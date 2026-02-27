#!/usr/bin/env python3
"""Build cards.json and embeddings.bin from the local Anki collection."""

import json
import re
import sqlite3
import struct
import sys
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer

ANKI_DB = Path.home() / "Library/Application Support/Anki2/User 1/collection.anki2"
OUT_DIR = Path(__file__).resolve().parent.parent / "assets" / "anki"

EXCLUDED_DECK_IDS = {
    1737667062461,   # RTK
    1754858565860,   # N２文法（全部の文章の型）
}

FIELD_SEP = "\x1f"

# Notetype field index mappings: notetype_id -> {key: field_index}
# w=word, r=reading, m=meaning, s=sentence
NOTETYPE_FIELDS = {
    # Japanese sentences: VocabKanji(4), VocabFurigana(5), VocabDef(8), SentKanji(0)
    1666627418178: {"w": 4, "r": 5, "m": 8, "s": 0},
    # Kaishi 1.5k: Word(0), Word Reading(1), Word Meaning(2), Sentence(5)
    1708628080880: {"w": 0, "r": 1, "m": 2, "s": 5},
    # (deprecated) Words I find in the wild: Word(0), Word furigana(1), Meaning(2), Sentence(3)
    1741510848189: {"w": 0, "r": 1, "m": 2, "s": 3},
    # カルテット: Word(0), Word furigana(1), Meaning(2), Sentence(3)
    1745471825167: {"w": 0, "r": 1, "m": 2, "s": 3},
    # 発見した言葉: Word(0), Meaning(1), Word furigana(2), Sentence(3)
    1746666659171: {"w": 0, "r": 2, "m": 1, "s": 3},
}

SOUND_RE = re.compile(r"\[sound:.*?\]")
HTML_RE = re.compile(r"<[^>]+>")


def strip_markup(text: str) -> str:
    text = SOUND_RE.sub("", text)
    text = HTML_RE.sub("", text)
    return text.strip()


def get_field(fields: list[str], idx: int | None) -> str:
    if idx is None or idx >= len(fields):
        return ""
    return strip_markup(fields[idx])


def main():
    if not ANKI_DB.exists():
        print(f"Anki database not found: {ANKI_DB}", file=sys.stderr)
        sys.exit(1)

    # Open read-only so it works even if Anki is running
    conn = sqlite3.connect(f"file:{ANKI_DB}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row

    # Build deck name lookup
    decks = {r["id"]: r["name"] for r in conn.execute("SELECT id, name FROM decks")}

    # Get all cards with their notes, excluding certain decks.
    # Deduplicate by note ID (a note can have multiple cards).
    rows = conn.execute(
        """
        SELECT DISTINCT n.id AS nid, n.mid, n.flds, c.did
        FROM cards c
        JOIN notes n ON c.nid = n.id
        WHERE c.did NOT IN ({})
        """.format(",".join("?" * len(EXCLUDED_DECK_IDS))),
        list(EXCLUDED_DECK_IDS),
    ).fetchall()
    conn.close()

    # Deduplicate by note ID, keeping first occurrence
    seen_nids = set()
    cards = []
    for row in rows:
        nid = row["nid"]
        if nid in seen_nids:
            continue
        seen_nids.add(nid)

        mid = row["mid"]
        mapping = NOTETYPE_FIELDS.get(mid)
        if mapping is None:
            continue

        fields = row["flds"].split(FIELD_SEP)
        w = get_field(fields, mapping["w"])
        r = get_field(fields, mapping.get("r"))
        m = get_field(fields, mapping["m"])
        s = get_field(fields, mapping.get("s"))
        d = decks.get(row["did"], "")

        if not w and not m:
            continue

        cards.append({"w": w, "r": r, "m": m, "s": s, "d": d})

    print(f"Extracted {len(cards)} cards")

    # Compute embeddings
    model = SentenceTransformer("intfloat/multilingual-e5-small")
    texts = [f"passage: {c['w']} {c['m']} {c['s']}" for c in cards]

    print("Computing embeddings...")
    embeddings = model.encode(texts, show_progress_bar=True, normalize_embeddings=True)
    embeddings = embeddings.astype(np.float32)

    # Write output
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    json_path = OUT_DIR / "cards.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(cards, f, ensure_ascii=False)
    print(f"Wrote {json_path} ({json_path.stat().st_size / 1024 / 1024:.1f} MB)")

    bin_path = OUT_DIR / "embeddings.bin"
    with open(bin_path, "wb") as f:
        f.write(embeddings.tobytes())
    print(f"Wrote {bin_path} ({bin_path.stat().st_size / 1024 / 1024:.1f} MB)")


if __name__ == "__main__":
    main()
