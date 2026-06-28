#!/usr/bin/env python3
"""Build the reading (furigana) index and kana embeddings.

This is a second layer on top of build_anki_embeddings.py. It normalizes each
card's furigana reading to plain hiragana so that a kana query (ちゅうとはんぱ)
can match a kanji card (中途半端), and computes ruri embeddings over the reading
string for fuzzy phonetic matching.

Run build_anki_embeddings.py first (or alongside) so cards.json exists and stays
aligned by index with the files written here.
"""

import json
import unicodedata

from sentence_transformers import SentenceTransformer

from anki_common import OUT_DIR, load_cards, write_bin

# Hiragana and katakana blocks.
KATAKANA_START = 0x30A1
KATAKANA_END = 0x30F6
KANA_OFFSET = 0x60  # katakana -> hiragana


def to_hiragana(text: str) -> str:
    out = []
    for ch in text:
        code = ord(ch)
        if KATAKANA_START <= code <= KATAKANA_END:
            out.append(chr(code - KANA_OFFSET))
        else:
            out.append(ch)
    return "".join(out)


def reading_key(reading: str, word: str) -> str:
    """Normalize a card to a plain-hiragana reading string.

    Prefers the furigana field; falls back to the word if it's already kana.
    Returns "" if nothing usable is found.
    """
    src = reading or word
    if not src:
        return ""
    src = unicodedata.normalize("NFKC", src)
    src = to_hiragana(src)
    # keep only kana and the long-vowel mark; drop spaces, punctuation, kanji
    kept = [c for c in src if "぀" <= c <= "ゟ" or c == "ー"]
    return "".join(kept)


def main():
    cards = load_cards()
    print(f"Extracted {len(cards)} cards")

    readings = [reading_key(c["r"], c["w"]) for c in cards]
    have = sum(1 for k in readings if k)
    print(f"Reading keys: {have}/{len(readings)} non-empty")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    readings_path = OUT_DIR / "readings.json"
    with open(readings_path, "w", encoding="utf-8") as f:
        json.dump(readings, f, ensure_ascii=False)
    print(f"Wrote readings.json ({readings_path.stat().st_size / 1024:.0f} KB)")

    # Kana embeddings via ruri. Embed the reading string; fall back to the word
    # for cards with no reading so the row still has a usable vector.
    print("\n[ruri kana] Computing embeddings...")
    ruri = SentenceTransformer("cl-nagoya/ruri-v3-30m")
    texts = [k if k else c["w"] for k, c in zip(readings, cards)]
    emb = ruri.encode(texts, show_progress_bar=True, normalize_embeddings=True)
    write_bin(OUT_DIR / "emb_ruri_kana.bin", emb)  # 256-dim
    del ruri

    print("\nDone!")


if __name__ == "__main__":
    main()
