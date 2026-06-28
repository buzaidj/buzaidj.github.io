
import requests
import re
import os
import html


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
FORVO_API_KEY = ENV.get("FORVO_API_KEY", "")
DECK_NAMES = ["発見した言葉"]
AUDIO_FIELD = "Audio"
WORD_FIELD = "Word"
SENTENCE_FIELD = "Sentence"  # Field to check for **bold** markers
ANKI_MEDIA_DIR = os.path.expanduser(
    ENV.get("ANKI_MEDIA_DIR", "~/Library/Application Support/Anki2/User 1/collection.media")
)

def clean_word(word):
    word = html.unescape(word)
    word = re.sub(r'<[^>]+>', '', word)
    word = re.sub(r'\[.*?\]', '', word)
    word = re.sub(r'（.*?）', '', word)
    word = re.sub(r'[^\wぁ-んァ-ン一-龯ー]', '', word)
    return word.strip()

def convert_bold_markers(text):
    """Convert **text** markdown to <b>text</b> HTML tags"""
    return re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)

def query_anki_notes(deck_name):
    payload = {
        "action": "findNotes",
        "version": 6,
        "params": {
            "query": f'deck:"{deck_name}"'
        }
    }
    return requests.post(ANKI_CONNECT_URL, json=payload).json()["result"]

def get_note_fields(note_ids):
    payload = {
        "action": "notesInfo",
        "version": 6,
        "params": {
            "notes": note_ids
        }
    }
    return requests.post(ANKI_CONNECT_URL, json=payload).json()["result"]

def fetch_audio_from_forvo(word):
    url = f"https://apifree.forvo.com/key/{FORVO_API_KEY}/format/json/action/word-pronunciations/word/{word}/language/ja"
    res = requests.get(url)
    if res.status_code != 200:
        return None
    data = res.json()
    items = data.get("items", [])
    if not items:
        return None
    return items[0]["pathmp3"]

def download_audio(url, filename):
    audio = requests.get(url).content
    with open(os.path.join(ANKI_MEDIA_DIR, filename), "wb") as f:
        f.write(audio)

def update_anki_note(note_id, audio_filename):
    audio_tag = f"[sound:{audio_filename}]"
    payload = {
        "action": "updateNoteFields",
        "version": 6,
        "params": {
            "note": {
                "id": note_id,
                "fields": {
                    AUDIO_FIELD: audio_tag
                }
            }
        }
    }
    requests.post(ANKI_CONNECT_URL, json=payload)

def update_note_field(note_id, field_name, new_value):
    """Update any field on a note"""
    payload = {
        "action": "updateNoteFields",
        "version": 6,
        "params": {
            "note": {
                "id": note_id,
                "fields": {
                    field_name: new_value
                }
            }
        }
    }
    requests.post(ANKI_CONNECT_URL, json=payload)

def mark_audio_unavailable(note_id):
    payload = {
        "action": "updateNoteFields",
        "version": 6,
        "params": {
            "note": {
                "id": note_id,
                "fields": {
                    AUDIO_FIELD: "    "
                }
            }
        }
    }
    requests.post(ANKI_CONNECT_URL, json=payload)

def process_bold_markers(notes):
    """Loop through all cards and replace **text** with <b>text</b>"""
    print("\n=== Processing bold markers ===")
    for note in notes:
        fields_to_check = note['fields']
        updated = False

        for field_name, field_data in fields_to_check.items():
            original_value = field_data['value']
            if '**' in original_value:
                new_value = convert_bold_markers(original_value)
                if new_value != original_value:
                    update_note_field(note['noteId'], field_name, new_value)
                    print(f"Updated bold in '{field_name}' for note {note['noteId']}")
                    print(f"  Before: {original_value[:80]}...")
                    print(f"  After:  {new_value[:80]}...")
                    updated = True

        if not updated and any('**' in f['value'] for f in fields_to_check.values()):
            print(f"Note {note['noteId']} had ** but no changes made")

def main():
    for deck_name in DECK_NAMES:
        print(f"Processing deck: {deck_name}")
        note_ids = query_anki_notes(deck_name)
        if not note_ids:
            print(f"No notes to update in deck: {deck_name}")
            continue

        notes = get_note_fields(note_ids)

        # First loop: Process bold markers in all fields
        process_bold_markers(notes)

        # Second loop: Process audio (original functionality)
        print("\n=== Processing audio ===")
        for note in notes:
            word_raw = note['fields'][WORD_FIELD]['value']
            word = clean_word(word_raw)

            audio_field_value = note['fields'][AUDIO_FIELD]['value']
            if audio_field_value:
                continue

            print(f"Searching Forvo for: {word}")
            audio_url = fetch_audio_from_forvo(word)
            if audio_url:
                audio_filename = f"anki_audio_{note['noteId']}.mp3"
                filepath = os.path.join(ANKI_MEDIA_DIR, audio_filename)

                if os.path.exists(filepath):
                    print(f"File already downloaded for {word} — reusing.")
                else:
                    download_audio(audio_url, audio_filename)
                    print(f"Downloaded audio for {word}")

                update_anki_note(note['noteId'], audio_filename)
                print(f"Updated {word}")
            else:
                print(f"No audio found for {word}")
                mark_audio_unavailable(note['noteId'])
                print(f"Marked {word} as 'null' to skip in the future")

if __name__ == "__main__":
    main()
