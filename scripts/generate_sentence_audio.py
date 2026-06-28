#!/usr/bin/env python3
"""Generate sentence audio via ElevenLabs for 発見した言葉 cards missing it.

Processes cards from most recent to oldest, rotating between voices.
Stops when the character limit is reached.
"""

import html
import json
import os
import random
import re
import requests
import sys
import time

ANKI_CONNECT_URL = "http://localhost:8765"
DECK_NAME = "発見した言葉"
MODEL_NAME = "発見した言葉"
ANKI_MEDIA_DIR = os.path.expanduser(
    "~/Library/Application Support/Anki2/User 1/collection.media"
)

ELEVENLABS_API_URL = "https://api.elevenlabs.io/v1/text-to-speech"
ELEVENLABS_MODEL = "eleven_multilingual_v2"
VOICES = [
    ("Hinata", "j210dv0vWm7fCknyQpbA"),
    ("Morioki", "8EkOjt4xTPGMclNlh1pk"),
    ("Ishibashi", "Mv8AjrYZCBkdsmDHNwcB"),
]

DEFAULT_CHAR_LIMIT = 10_000


def load_api_key():
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    with open(env_path) as f:
        for line in f:
            if line.startswith("ELEVENLABS_API_KEY="):
                return line.strip().split("=", 1)[1]
    print("ELEVENLABS_API_KEY not found in .env")
    sys.exit(1)


def anki_request(action, **params):
    res = requests.post(
        ANKI_CONNECT_URL, json={"action": action, "version": 6, "params": params}
    ).json()
    if res.get("error"):
        raise RuntimeError(f"AnkiConnect error: {res['error']}")
    return res["result"]


def get_missing_notes():
    """Get notes missing sentence audio, sorted most recent first."""
    note_ids = anki_request(
        "findNotes",
        query=f'deck:"{DECK_NAME}" note:"{MODEL_NAME}" -"Sentence Audio:_*"',
    )
    note_ids.sort(reverse=True)
    return note_ids


def clean_sentence(sentence):
    """Clean sentence text for TTS: strip HTML, entities, furigana brackets, context notes."""
    s = re.sub(r"<[^>]+>", "", sentence)  # HTML tags
    s = html.unescape(s)  # &nbsp; etc
    s = re.sub(r"\[([^\]]*[a-zA-Z\d|][^\]]*)\]", "", s)  # [context/footnotes] containing ASCII, digits, or pipes
    s = re.sub(r"(\S)\[([^\]]+)\]", r"\1", s)  # furigana like 煩悶[はんもん] — keep kanji, drop reading
    s = re.sub(r"^\[([^\]]+)\]\s*", "", s)  # leading [context] brackets
    s = re.sub(r"^[a-zA-Z]:\s*", "", s, flags=re.MULTILINE)  # dialogue markers like "a: " "b: "
    s = re.sub(r"\s+", " ", s)  # collapse whitespace
    return s.strip()


def generate_audio(text, voice_id, api_key):
    """Call ElevenLabs TTS and return audio bytes."""
    url = f"{ELEVENLABS_API_URL}/{voice_id}"
    headers = {"Accept": "audio/mpeg", "xi-api-key": api_key}
    data = {
        "text": text,
        "model_id": ELEVENLABS_MODEL,
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.8,
            "style": 0.0,
        },
    }
    res = requests.post(url, headers=headers, json=data)
    if res.status_code != 200:
        raise RuntimeError(f"ElevenLabs API error {res.status_code}: {res.text[:200]}")
    return res.content


def save_audio(audio_bytes, note_id):
    """Save audio to Anki media folder and return the filename."""
    filename = f"sentence_audio_{note_id}.mp3"
    filepath = os.path.join(ANKI_MEDIA_DIR, filename)
    with open(filepath, "wb") as f:
        f.write(audio_bytes)
    return filename


def update_sentence_audio(note_id, filename):
    """Set the Sentence Audio field on a note."""
    anki_request(
        "updateNoteFields",
        note={
            "id": note_id,
            "fields": {"Sentence Audio": f"[sound:{filename}]"},
        },
    )


def main():
    char_limit = DEFAULT_CHAR_LIMIT
    if len(sys.argv) > 1:
        char_limit = int(sys.argv[1])

    api_key = load_api_key()

    print(f"Character limit: {char_limit:,}")
    print("Finding cards missing sentence audio...")

    note_ids = get_missing_notes()
    if not note_ids:
        print("All cards already have sentence audio!")
        return

    notes = anki_request("notesInfo", notes=note_ids)

    # Build work list
    work = []
    for note in notes:
        sentence = clean_sentence(note["fields"].get("Sentence", {}).get("value", ""))
        if not sentence:
            continue
        work.append((note["noteId"], note["fields"]["Word"]["value"], sentence))

    chars_used = 0
    to_process = []
    for note_id, word, sentence in work:
        if chars_used + len(sentence) > char_limit:
            break
        chars_used += len(sentence)
        to_process.append((note_id, word, sentence))

    print(f"\nWill generate audio for {len(to_process)} cards ({chars_used:,} chars)")
    print(f"Remaining after this run: {len(work) - len(to_process)} cards\n")

    if not to_process:
        print("Nothing to process within the character limit.")
        return

    # Preview
    for i, (note_id, word, sentence) in enumerate(to_process[:10]):
        print(f"  {i+1}. {word}: {sentence[:50]}")
    if len(to_process) > 10:
        print(f"  ... and {len(to_process) - 10} more")

    response = input("\nProceed? (y/n): ").strip().lower()
    if response != "y":
        print("Aborted.")
        return

    print()
    succeeded = 0
    failed = 0
    for i, (note_id, word, sentence) in enumerate(to_process):
        voice_name, voice_id = random.choice(VOICES)
        try:
            audio = generate_audio(sentence, voice_id, api_key)
            filename = save_audio(audio, note_id)
            update_sentence_audio(note_id, filename)
            succeeded += 1
            print(f"  [{i+1}/{len(to_process)}] {word} ✓ ({voice_name}, {len(sentence)} chars)")
        except Exception as e:
            failed += 1
            print(f"  [{i+1}/{len(to_process)}] {word} ✗ {e}")
        # Rate limit to avoid hitting ElevenLabs throttling
        if i < len(to_process) - 1:
            time.sleep(0.5)

    print(f"\nDone! Generated: {succeeded}, Failed: {failed}, Chars used: {chars_used:,}")


if __name__ == "__main__":
    main()
