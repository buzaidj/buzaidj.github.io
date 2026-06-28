import html
import re
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

import numpy as np

ANKI_DB = Path.home() / "Library/Application Support/Anki2/User 1/collection.anki2"
OUT_DIR = Path(__file__).resolve().parent.parent / "assets" / "anki"

EXCLUDED_DECK_IDS = {
    1737667062461,   # RTK
    1754858565860,   # N２文法（全部の文章の型）
}

FIELD_SEP = "\x1f"

NOTETYPE_FIELDS = {
    1666627418178: {"w": 4, "r": 5, "m": 8, "s": 0},
    1708628080880: {"w": 0, "r": 3, "m": 2, "s": 5},
    1741510848189: {"w": 0, "r": 1, "m": 2, "s": 3},
    1745471825167: {"w": 0, "r": 1, "m": 2, "s": 3},
    1746666659171: {"w": 0, "r": 2, "m": 1, "s": 3},
}

SOUND_RE = re.compile(r"\[sound:.*?\]")
HTML_RE = re.compile(r"<[^>]+>")


def strip_markup(text: str) -> str:
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


def load_cards():
    if not ANKI_DB.exists():
        print(f"Anki database not found: {ANKI_DB}", file=sys.stderr)
        sys.exit(1)

    with tempfile.NamedTemporaryFile(suffix=".anki2", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    shutil.copy2(ANKI_DB, tmp_path)
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
        for suffix in ("-wal", "-shm"):
            (tmp_path.parent / (tmp_path.name + suffix)).unlink(missing_ok=True)

    seen_nids = set()
    cards = []
    for row in rows:
        nid = row["nid"]
        if nid in seen_nids:
            continue
        seen_nids.add(nid)
        mapping = NOTETYPE_FIELDS.get(row["mid"])
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
    return cards
