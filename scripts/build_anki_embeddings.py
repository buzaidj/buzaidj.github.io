#!/usr/bin/env python3
"""Build cards.json and embedding files from the local Anki collection."""

import json

from sentence_transformers import SentenceTransformer

import build_kana_phon_table
import build_reading_index
from anki_common import OUT_DIR, load_cards, write_bin


def main():
    cards = load_cards()
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
    build_reading_index.main()
    build_kana_phon_table.main()
