#!/usr/bin/env python3
"""Pull vocab entries from Google Keep, generate furigana via claude CLI, and upsert into Anki."""

import gkeepapi
import json
import os
import re
import subprocess
import sys
import requests

def load_env():
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    env = {}
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env


ENV = load_env()

ANKI_CONNECT_URL = "http://localhost:8765"
DECK_NAME = "発見した言葉"
MODEL_NAME = "発見した言葉"
KEEP_EMAIL = ENV.get("KEEP_EMAIL", "")
KEEP_TOKEN_PATH = os.path.expanduser(ENV.get("KEEP_TOKEN_PATH", "~/.config/gkeep_master_token"))
KEEP_NOTE_TITLE = "ことば"


def get_keep_note():
    """Authenticate to Google Keep and return the most recent ことば note."""
    with open(KEEP_TOKEN_PATH) as f:
        master_token = f.read().strip()

    keep = gkeepapi.Keep()
    keep.authenticate(KEEP_EMAIL, master_token)

    notes = []
    for note in keep.find(query=KEEP_NOTE_TITLE):
        if note.title.startswith(KEEP_NOTE_TITLE) and not note.archived and not note.trashed:
            notes.append(note)

    if not notes:
        print("No ことば notes found in Google Keep.")
        sys.exit(1)

    # Sort by timestamp (most recently edited first)
    notes.sort(key=lambda n: n.timestamps.edited, reverse=True)
    return notes[0]


def parse_entries(text):
    """Parse Keep note text into entries. Each entry is separated by a blank line.

    Format per entry:
      word
      meaning
      example sentence (optional, may be 例文なし or absent)
    """
    blocks = re.split(r'\n\s*\n', text.strip())
    entries = []

    for block in blocks:
        lines = [l.strip() for l in block.strip().split('\n') if l.strip()]
        if not lines:
            continue

        word = lines[0]
        meaning = lines[1] if len(lines) > 1 else ""
        sentence = lines[2] if len(lines) > 2 else ""

        # Skip entries with no real sentence
        if sentence.lower() in ("例文なし", "例文なく"):
            sentence = ""

        entries.append({
            "word": word,
            "meaning": meaning,
            "sentence": sentence,
        })

    return entries


def generate_furigana(entries):
    """Call claude CLI to generate furigana and bold markers for all entries."""
    # Build the prompt with all entries
    entries_text = ""
    for i, e in enumerate(entries):
        entries_text += f"Entry {i+1}:\n"
        entries_text += f"  Word: {e['word']}\n"
        entries_text += f"  Meaning: {e['meaning']}\n"
        entries_text += f"  Sentence: {e['sentence']}\n\n"

    prompt = f"""I have Japanese vocabulary entries. For each entry I give you a word, meaning, and sentence. Your job is to produce three fields:

1. "word_furigana": Add furigana in brackets after each kanji or kanji compound. Use half-width space before each kanji group. Examples:
   - 口を噤む -> 口[くち]を 噤[つぐ]む
   - 介在 -> 介在[かいざい]
   - 取り上げる -> 取[と]り 上[あ]げる
   - がつがつ -> がつがつ (pure kana, no change)
   If the word already has furigana in brackets like 峻厳[しゅんげん], preserve it exactly.

2. "sentence_with_bold": The EXACT original sentence with the target word (or its conjugated form as it appears) wrapped in <b></b> tags. Do NOT change the sentence text. If the sentence is empty, return "".

3. "sentence_furigana": The sentence with furigana added to ALL kanji in the same bracket format. Separate each word/particle with a space. Do NOT add bold tags here. If the sentence is empty, return "".

RULES:
- The word and meaning I give you are LAW. Do not modify them.
- You are ONLY inferring the furigana fields.
- Return ONLY a JSON array with objects having these exact keys: "word_furigana", "sentence_with_bold", "sentence_furigana". One object per entry, in order.
- No markdown code fences, no explanation, just the raw JSON array.

Here are the entries:

{entries_text}"""

    result = subprocess.run(
        ["claude", "--print", "--model", "claude-opus-4-6"],
        input=prompt,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        print(f"claude CLI error: {result.stderr}")
        sys.exit(1)

    output = result.stdout.strip()

    # Strip markdown code fences if present
    if output.startswith("```"):
        output = re.sub(r'^```\w*\n?', '', output)
        output = re.sub(r'\n?```$', '', output)

    # Strip any preamble text before the JSON array
    bracket_idx = output.find("[")
    if bracket_idx > 0:
        output = output[bracket_idx:]

    try:
        furigana_data = json.loads(output)
    except json.JSONDecodeError:
        print("Failed to parse claude output as JSON:")
        print(output)
        sys.exit(1)

    if len(furigana_data) != len(entries):
        print(f"Expected {len(entries)} entries but got {len(furigana_data)} from claude")
        sys.exit(1)

    return furigana_data


def add_to_anki(entries, furigana_data):
    """Add notes to Anki via AnkiConnect."""
    added = 0
    skipped = 0

    for entry, furi in zip(entries, furigana_data):
        word = entry["word"]
        # Strip any existing furigana brackets from the word for the Word field
        clean_word = re.sub(r'\[.*?\]', '', word).strip()

        # Check if this word already exists in Anki
        search_payload = {
            "action": "findNotes",
            "version": 6,
            "params": {
                "query": f'deck:"{DECK_NAME}" Word:"{clean_word}"'
            }
        }
        res = requests.post(ANKI_CONNECT_URL, json=search_payload).json()
        if res.get("result"):
            print(f"  Skipping (already exists): {clean_word}")
            skipped += 1
            continue

        note_payload = {
            "action": "addNote",
            "version": 6,
            "params": {
                "note": {
                    "deckName": DECK_NAME,
                    "modelName": MODEL_NAME,
                    "fields": {
                        "Word": clean_word,
                        "Meaning": entry["meaning"],
                        "Word furigana": furi["word_furigana"],
                        "Sentence": furi["sentence_with_bold"],
                        "Sentence furigana": furi["sentence_furigana"],
                    },
                    "options": {
                        "allowDuplicate": False,
                    }
                }
            }
        }

        res = requests.post(ANKI_CONNECT_URL, json=note_payload).json()
        if res.get("error"):
            print(f"  Error adding {clean_word}: {res['error']}")
        else:
            print(f"  Added: {clean_word}")
            added += 1

    return added, skipped


def check_anki_connection():
    """Verify AnkiConnect is reachable before doing anything expensive."""
    try:
        requests.post(ANKI_CONNECT_URL, json={"action": "version", "version": 6}, timeout=3)
    except requests.ConnectionError:
        print("AnkiConnect not reachable. Is Anki open?")
        sys.exit(1)


def main():
    check_anki_connection()

    print("Fetching from Google Keep...")
    note = get_keep_note()

    print(f"\nMost recent note: \"{note.title}\"")
    print(f"Last edited: {note.timestamps.edited}")

    entries = parse_entries(note.text)
    print(f"Found {len(entries)} entries:\n")
    for e in entries:
        print(f"  {e['word']} — {e['meaning'][:40]}")
    print()

    response = input("Import these entries? (y/n): ").strip().lower()
    if response != "y":
        print("Aborted.")
        sys.exit(0)

    print("\nGenerating furigana via claude...")
    furigana_data = generate_furigana(entries)

    # Show a preview
    print("\nPreview:")
    for entry, furi in zip(entries, furigana_data):
        clean_word = re.sub(r'\[.*?\]', '', entry["word"]).strip()
        print(f"  {clean_word}")
        print(f"    Word furigana:     {furi['word_furigana']}")
        print(f"    Sentence:          {furi['sentence_with_bold']}")
        print(f"    Sentence furigana: {furi['sentence_furigana']}")
        print()

    response = input("Add to Anki? (y/n): ").strip().lower()
    if response != "y":
        print("Aborted.")
        sys.exit(0)

    print("\nAdding to Anki...")
    added, skipped = add_to_anki(entries, furigana_data)

    print(f"\nDone! Added: {added}, Skipped: {skipped}")


if __name__ == "__main__":
    main()
