#!/usr/bin/env python3
"""Build cards.json and embedding files from the local Anki collection."""

import json
import re
import shutil
import sqlite3
import sys
import tempfile
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
    # Kaishi 1.5k: Word(0), Word Furigana(3), Word Meaning(2), Sentence(5)
    1708628080880: {"w": 0, "r": 3, "m": 2, "s": 5},
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
    import html
    text = SOUND_RE.sub("", text)
    text = HTML_RE.sub("", text)
    text = html.unescape(text)
    return text.strip()


def get_field(fields: list[str], idx: int | None) -> str:
    if idx is None or idx >= len(fields):
        return ""
    return strip_markup(fields[idx])


def write_bin(path, embeddings):
    with open(path, "wb") as f:
        f.write(embeddings.astype(np.float32).tobytes())
    print(f"  {path.name} ({path.stat().st_size / 1024 / 1024:.1f} MB)")


def main():
    if not ANKI_DB.exists():
        print(f"Anki database not found: {ANKI_DB}", file=sys.stderr)
        sys.exit(1)

    # Copy the DB to a temp file to avoid locking issues when Anki is open
    with tempfile.NamedTemporaryFile(suffix=".anki2", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    shutil.copy2(ANKI_DB, tmp_path)
    # Also copy the WAL file if it exists so we get a consistent snapshot
    wal = ANKI_DB.parent / (ANKI_DB.name + "-wal")
    if wal.exists():
        shutil.copy2(wal, tmp_path.parent / (tmp_path.name + "-wal"))

    try:
        conn = sqlite3.connect(str(tmp_path))
        conn.row_factory = sqlite3.Row

        decks = {r["id"]: r["name"] for r in conn.execute("SELECT id, name FROM decks")}

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
    finally:
        tmp_path.unlink(missing_ok=True)
        wal_tmp = tmp_path.parent / (tmp_path.name + "-wal")
        wal_tmp.unlink(missing_ok=True)
        shm_tmp = tmp_path.parent / (tmp_path.name + "-shm")
        shm_tmp.unlink(missing_ok=True)

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

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    json_path = OUT_DIR / "cards.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(cards, f, ensure_ascii=False)
    print(f"Wrote cards.json ({json_path.stat().st_size / 1024 / 1024:.1f} MB)")

    # --- Model 1: multilingual-e5-small ---
    print("\n[e5-small] Computing embeddings...")
    e5s = SentenceTransformer("intfloat/multilingual-e5-small")
    e5s_texts = [f"passage: {c['w']} {c['m']} {c['s']}" for c in cards]
    e5s_emb = e5s.encode(e5s_texts, show_progress_bar=True, normalize_embeddings=True)
    write_bin(OUT_DIR / "emb_e5s.bin", e5s_emb)  # 384-dim
    del e5s

    # --- Model 2: multilingual-e5-base ---
    print("\n[e5-base] Computing embeddings...")
    e5b = SentenceTransformer("intfloat/multilingual-e5-base")
    e5b_texts = [f"passage: {c['w']} {c['m']} {c['s']}" for c in cards]
    e5b_emb = e5b.encode(e5b_texts, show_progress_bar=True, normalize_embeddings=True)
    write_bin(OUT_DIR / "emb_e5b.bin", e5b_emb)  # 768-dim
    del e5b

    # --- Model 3: ruri-v3-30m (Japanese) ---
    print("\n[ruri-v3-30m] Computing embeddings...")
    ruri = SentenceTransformer("cl-nagoya/ruri-v3-30m")
    ruri_texts = [f"{c['w']} {c['s']}" for c in cards]
    ruri_emb = ruri.encode(ruri_texts, show_progress_bar=True, normalize_embeddings=True)
    write_bin(OUT_DIR / "emb_ruri.bin", ruri_emb)  # 256-dim
    del ruri

    print("\nDone!")


if __name__ == "__main__":
    main()
