import requests
import re
import html
import sys
import os


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
PITCH_FIELD = "Pitch Accent"
WORD_FIELD = "Word"
FURIGANA_FIELD = "Word furigana"
ACCENTS_FILE = os.path.expanduser(ENV.get("ACCENTS_FILE", "~/Downloads/kanjium_accents.txt"))

# --- Mora splitting ---

# Small kana that combine with a preceding kana to form one mora
COMBO_KANA = set("ゃゅょャュョぁぃぅぇぉァィゥェォ")

def split_morae(kana):
    """Split a kana string into morae. Handles youon (きゃ = 1 mora)."""
    morae = []
    i = 0
    while i < len(kana):
        mora = kana[i]
        # Check if next char is a small kana that combines
        if i + 1 < len(kana) and kana[i + 1] in COMBO_KANA:
            mora += kana[i + 1]
            i += 2
        else:
            i += 1
        morae.append(mora)
    return morae


# --- Pitch pattern to High/Low list ---

def accent_to_hl(morae_count, accent_pos):
    """
    Convert accent position number to H/L pattern.
    accent_pos 0 = heiban (flat): LHHH...H
    accent_pos 1 = atamadaka: HLLL...L
    accent_pos N = nakadaka/odaka: LHHHLL...L (drop after mora N)
    """
    if morae_count == 0:
        return []
    if morae_count == 1:
        if accent_pos == 1 or accent_pos == 0:
            return ['H']
        return ['H']

    if accent_pos == 0:  # heiban
        return ['L'] + ['H'] * (morae_count - 1)
    elif accent_pos == 1:  # atamadaka
        return ['H'] + ['L'] * (morae_count - 1)
    else:  # nakadaka or odaka
        pattern = ['L']
        for i in range(1, morae_count):
            if i < accent_pos:
                pattern.append('H')
            else:
                pattern.append('L')
        return pattern


# --- HTML generation ---

def generate_pitch_html(reading, accent_pos):
    """
    Generate HTML with pitch accent visualization.
    Uses SVG-style lines above/below the kana to show pitch contour.
    """
    morae = split_morae(reading)
    n = len(morae)
    if n == 0:
        return ""

    pattern = accent_to_hl(n, accent_pos)

    # Build HTML with CSS classes for high/low pitch
    # We draw a line above high morae and below low morae,
    # with connecting lines at transitions
    html_parts = []
    html_parts.append('<span class="pitch-accent">')

    for i, (mora, hl) in enumerate(zip(morae, pattern)):
        prev_hl = pattern[i - 1] if i > 0 else None
        next_hl = pattern[i + 1] if i + 1 < n else None

        classes = ["pa-mora"]
        if hl == 'H':
            classes.append("pa-high")
        else:
            classes.append("pa-low")

        # Add connector classes for drawing the step between morae
        if prev_hl and prev_hl != hl:
            if hl == 'H':
                classes.append("pa-rise")  # step up before this mora
            else:
                classes.append("pa-drop")  # step down before this mora

        html_parts.append(f'<span class="{" ".join(classes)}">{mora}</span>')

    # For heiban words, add a trailing indicator showing pitch continues high
    if accent_pos == 0 and n > 1:
        html_parts.append('<span class="pa-mora pa-high pa-heiban-tail">&#x2192;</span>')

    html_parts.append('</span>')
    return "".join(html_parts)


def generate_pitch_html_simple(reading, accent_pos):
    """
    Generate HTML using overline/underline borders to show pitch.
    This is a simpler approach that works well in Anki without
    requiring any custom CSS in the card template - it's all inline.
    """
    morae = split_morae(reading)
    n = len(morae)
    if n == 0:
        return ""

    pattern = accent_to_hl(n, accent_pos)

    parts = []

    for i, (mora, hl) in enumerate(zip(morae, pattern)):
        prev_hl = pattern[i - 1] if i > 0 else None
        next_hl = pattern[i + 1] if i + 1 < n else None

        # Determine borders
        styles = [
            "display:inline-block",
            "position:relative",
        ]

        if hl == 'H':
            styles.append("border-top:2px solid #e53935")
        else:
            styles.append("border-bottom:2px solid #e53935")

        # Add vertical connector line when pitch changes
        if prev_hl is not None and prev_hl != hl:
            styles.append("border-left:2px solid #e53935")

        # For the last mora, close the right side if it's a drop point
        # (odaka: accent_pos == n means drop happens after last mora)

        styles.append("padding:2px 1px")
        styles.append("line-height:1.4")
        styles.append("font-size:1.1em")

        style_str = ";".join(styles)
        parts.append(f'<span style="{style_str}">{mora}</span>')

    # heiban trailing arrow
    if accent_pos == 0 and n > 1:
        parts.append(
            '<span style="display:inline-block;border-top:2px solid #e53935;'
            'border-left:2px solid #e53935;padding:2px 1px;line-height:1.4;'
            'font-size:0.7em;color:#e53935;vertical-align:middle">&#x2197;</span>'
        )

    # downstep marker for odaka (accent == n, drop after last mora)
    if accent_pos == n and n > 0:
        parts.append(
            '<span style="display:inline-block;border-bottom:2px solid #e53935;'
            'border-left:2px solid #e53935;padding:2px 1px;line-height:1.4;'
            'font-size:0.7em;color:#e53935;vertical-align:middle">&#x2198;</span>'
        )

    accent_label = ""
    if accent_pos == 0:
        accent_label = "平板"
    elif accent_pos == 1:
        accent_label = "頭高"
    elif accent_pos == n:
        accent_label = "尾高"
    else:
        accent_label = "中高"

    result = "".join(parts)
    result += f'&nbsp;<span style="font-size:0.75em;color:#888">[{accent_pos}]</span>'

    return result


# --- Load accent dictionary ---

def load_accent_dict(filepath):
    """
    Load kanjium accents.txt into a dict.
    Key: (expression, reading) and also just (reading,) for kana-only lookups.
    Value: first accent number (int).
    """
    accent_dict = {}

    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split('\t')
            if len(parts) < 3:
                continue

            expression = parts[0]
            reading = parts[1]
            accent_raw = parts[2]

            # Parse accent: strip POS tags like (副), take the first number
            # Examples: "2", "0,2", "(副)0,(名)3"
            accent_str = re.sub(r'\([^)]*\)', '', accent_raw)
            numbers = [x.strip() for x in accent_str.split(',') if x.strip()]
            if not numbers:
                continue

            try:
                accent_pos = int(numbers[0])
            except ValueError:
                continue

            # Store by (expression, reading) for exact match
            key = (expression, reading)
            if key not in accent_dict:
                accent_dict[key] = accent_pos

            # Also store by expression alone (for when we don't have reading)
            if expression not in accent_dict:
                accent_dict[expression] = (reading, accent_pos)

    return accent_dict


# --- Extract reading from Anki furigana ---

def extract_reading(word, furigana):
    """
    Extract the full kana reading from Anki furigana format.
    Examples:
        店内[てんない] -> てんない
        代[か]わり -> かわり
        振[ふ]り 向[む]く -> ふりむく
        さっと -> さっと
    """
    furigana = html.unescape(furigana)
    furigana = re.sub(r'<[^>]+>', '', furigana)  # strip HTML tags

    # Remove spaces between furigana groups
    furigana = furigana.replace(' ', '')

    reading = ""
    i = 0
    while i < len(furigana):
        if furigana[i] == '[':
            # Found a bracket - extract the reading
            end = furigana.index(']', i)
            reading += furigana[i + 1:end]
            i = end + 1
        elif is_kanji(furigana[i]):
            # Kanji without furigana bracket - skip it
            # (shouldn't normally happen in well-formatted furigana)
            i += 1
        else:
            # Kana or other char - include directly
            reading += furigana[i]
            i += 1

    return reading


def is_kanji(char):
    cp = ord(char)
    return (0x4E00 <= cp <= 0x9FFF or
            0x3400 <= cp <= 0x4DBF or
            0xF900 <= cp <= 0xFAFF or
            0x20000 <= cp <= 0x2A6DF)


def clean_word(word):
    """Clean HTML and brackets from the word field."""
    word = html.unescape(word)
    word = re.sub(r'<[^>]+>', '', word)
    word = re.sub(r'\[.*?\]', '', word)
    word = re.sub(r'（.*?）', '', word)
    return word.strip()


# --- AnkiConnect helpers ---

def query_anki_notes(deck_name, model_name):
    payload = {
        "action": "findNotes",
        "version": 6,
        "params": {
            "query": f'deck:"{deck_name}" note:"{model_name}"'
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


def update_note_field(note_id, field_name, value):
    payload = {
        "action": "updateNoteFields",
        "version": 6,
        "params": {
            "note": {
                "id": note_id,
                "fields": {
                    field_name: value
                }
            }
        }
    }
    return requests.post(ANKI_CONNECT_URL, json=payload).json()


# --- Main ---

def main():
    dry_run = "--dry-run" in sys.argv
    limit = None
    for arg in sys.argv[1:]:
        if arg.startswith("--limit="):
            limit = int(arg.split("=")[1])

    print(f"Loading accent dictionary from {ACCENTS_FILE}...")
    accent_dict = load_accent_dict(ACCENTS_FILE)
    print(f"Loaded {len(accent_dict)} entries")

    print(f"\nQuerying Anki for notes in {DECK_NAME} (model: {MODEL_NAME})...")
    note_ids = query_anki_notes(DECK_NAME, MODEL_NAME)
    print(f"Found {len(note_ids)} notes")

    if limit:
        note_ids = note_ids[:limit]
        print(f"Limiting to first {limit} notes")

    # Fetch in batches to avoid overwhelming AnkiConnect
    batch_size = 100
    found = 0
    not_found = 0
    skipped = 0
    updated = 0
    errors = 0

    for batch_start in range(0, len(note_ids), batch_size):
        batch_ids = note_ids[batch_start:batch_start + batch_size]
        notes = get_note_fields(batch_ids)

        for note in notes:
            note_id = note['noteId']
            word_raw = note['fields'][WORD_FIELD]['value']
            furigana_raw = note['fields'][FURIGANA_FIELD]['value']
            existing_pitch = note['fields'][PITCH_FIELD]['value'].strip()

            word = clean_word(word_raw)

            # Skip if already has pitch accent data
            if existing_pitch:
                skipped += 1
                continue

            # Skip if no furigana
            if not furigana_raw.strip():
                not_found += 1
                if not dry_run:
                    print(f"  No furigana for: {word}")
                continue

            # Extract reading
            reading = extract_reading(word, furigana_raw)
            if not reading:
                not_found += 1
                if not dry_run:
                    print(f"  Could not extract reading for: {word} ({furigana_raw})")
                continue

            # Look up accent: try (word, reading), then just word
            accent_pos = None
            lookup_reading = reading  # the reading we'll use for HTML generation
            key = (word, reading)
            if key in accent_dict:
                accent_pos = accent_dict[key]
            elif word in accent_dict:
                dict_reading, dict_accent = accent_dict[word]
                accent_pos = dict_accent
            elif reading in accent_dict:
                # Try looking up by reading as expression (for kana-only words)
                dict_reading, dict_accent = accent_dict[reading]
                accent_pos = dict_accent

            # If not found, try stripping な, する, に from the end
            if accent_pos is None:
                for suffix, reading_suffix in [('な', 'な'), ('する', 'する'), ('に', 'に')]:
                    if word.endswith(suffix) and len(word) > len(suffix):
                        base_word = word[:-len(suffix)]
                        base_reading = reading[:-len(reading_suffix)] if reading.endswith(reading_suffix) else reading
                        if not base_reading:
                            base_reading = base_word
                        key2 = (base_word, base_reading)
                        if key2 in accent_dict:
                            accent_pos = accent_dict[key2]
                            lookup_reading = base_reading
                            break
                        elif base_word in accent_dict:
                            dict_reading, dict_accent = accent_dict[base_word]
                            accent_pos = dict_accent
                            lookup_reading = dict_reading
                            break
                        elif base_reading in accent_dict:
                            dict_reading, dict_accent = accent_dict[base_reading]
                            accent_pos = dict_accent
                            lookup_reading = dict_reading
                            break

            if accent_pos is None:
                not_found += 1
                continue

            found += 1

            # Generate HTML
            pitch_html = generate_pitch_html_simple(lookup_reading, accent_pos)

            if dry_run:
                print(f"  {word} ({lookup_reading}) -> accent {accent_pos}")
            else:
                result = update_note_field(note_id, PITCH_FIELD, pitch_html)
                if result.get("error"):
                    print(f"  ERROR updating {word}: {result['error']}")
                    errors += 1
                else:
                    updated += 1

        # Progress
        processed = batch_start + len(batch_ids)
        print(f"Progress: {processed}/{len(note_ids)} notes processed...")

    print(f"\n=== Summary ===")
    print(f"Total notes:  {len(note_ids)}")
    print(f"Found accent: {found}")
    print(f"Not found:    {not_found}")
    print(f"Skipped:      {skipped} (already had pitch accent)")
    if not dry_run:
        print(f"Updated:      {updated}")
        print(f"Errors:       {errors}")
    else:
        print("(dry run - no changes made)")


if __name__ == "__main__":
    main()
