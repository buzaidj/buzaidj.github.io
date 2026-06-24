#!/usr/bin/env python3
"""Build a kana -> phoneme-feature-vector lookup table for the JS phonetic scorer.

The browser query path can't run Epitran/PanPhon, so we precompute, for every
hiragana mora/unit, its PanPhon feature-vector sequence. JS then tokenizes a kana
string greedily (longest match first) and concatenates the precomputed vectors.

LIMITATION: Epitran transliterates whole words and applies context effects that
per-mora concatenation can't reproduce:
  - ん (ɴ) assimilates to the following consonant (e.g. ŋ before k, nasalized
    vowel before y) -- here it's always the isolated uvular nasal ɴ.
  - っ geminates the *following* consonant; here it's an isolated glottal stop ʔ.
  - ー / long vowels: ー maps to the length marker ː (which yields zero feature
    vectors in PanPhon), and a trailing う that lengthens a vowel in whole-word
    transcription is instead emitted as its own ɯ vowel vector.
This is acceptable; single-mora and identical-string distances stay exact, and
the relative ordering of whole-word matches is preserved.
"""

import json
from pathlib import Path

import epitran
import panphon

OUT = Path(__file__).resolve().parent.parent / "assets" / "anki" / "kana_phon.json"

# Base hiragana (gojuon), voiced/semi-voiced, small kana, and the long mark.
BASE = [
    "あ", "い", "う", "え", "お",
    "か", "き", "く", "け", "こ",
    "さ", "し", "す", "せ", "そ",
    "た", "ち", "つ", "て", "と",
    "な", "に", "ぬ", "ね", "の",
    "は", "ひ", "ふ", "へ", "ほ",
    "ま", "み", "む", "め", "も",
    "や", "ゆ", "よ",
    "ら", "り", "る", "れ", "ろ",
    "わ", "ゐ", "ゑ", "を", "ん",
    # dakuten
    "が", "ぎ", "ぐ", "げ", "ご",
    "ざ", "じ", "ず", "ぜ", "ぞ",
    "だ", "ぢ", "づ", "で", "ど",
    "ば", "び", "ぶ", "べ", "ぼ",
    # handakuten
    "ぱ", "ぴ", "ぷ", "ぺ", "ぽ",
    # small kana (used standalone if they ever appear unattached)
    "ぁ", "ぃ", "ぅ", "ぇ", "ぉ",
    "ゃ", "ゅ", "ょ", "っ", "ゎ",
    # long-vowel mark
    "ー",
]

# Yoon: consonant kana that combine with small ゃゅょ (and a few ぃ/ぇ extensions).
YOON_LEAD = [
    "き", "ぎ", "し", "じ", "ち", "ぢ", "に", "ひ", "び", "ぴ",
    "み", "り",
]
YOON_SMALL = ["ゃ", "ゅ", "ょ"]

# Extra combos that show up in loanword-ish hiragana (small あいうえお after a base).
EXTRA_SMALL = ["ぁ", "ぃ", "ぅ", "ぇ", "ぉ"]
EXTRA_LEAD = [
    "う", "ゔ", "て", "で", "と", "ど", "し", "じ", "ち", "ふ", "つ", "す",
]


def units():
    seen = set()
    out = []

    def add(u):
        if u not in seen:
            seen.add(u)
            out.append(u)

    for lead in YOON_LEAD:
        for small in YOON_SMALL:
            add(lead + small)
    for lead in EXTRA_LEAD:
        for small in EXTRA_SMALL:
            add(lead + small)
    for u in BASE:
        add(u)
    return out


def main():
    epi = epitran.Epitran("jpn-Hira")
    ft = panphon.FeatureTable()

    table = {}
    skipped = []
    for u in units():
        ipa = epi.transliterate(u)
        vecs = ft.word_to_vector_list(ipa, numeric=True)
        if not vecs:
            # ー (length marker) and any unit that yields no phonemes: skip it.
            skipped.append(u)
            continue
        table[u] = vecs

    weights = list(ft.weights)  # 22-length
    data = {
        "weights": weights,
        "indelCost": float(sum(weights)),
        "featureNames": [
            "syl", "son", "cons", "cont", "delrel", "lat", "nas", "strid",
            "voi", "sg", "cg", "ant", "cor", "distr", "lab", "hi", "lo",
            "back", "round", "velaric", "tense", "long", "hitone", "hireg",
        ],
        "table": table,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")))
    size = OUT.stat().st_size
    print(f"wrote {OUT} ({size} bytes, {len(table)} units)")
    print(f"indelCost={data['indelCost']} weights_len={len(weights)}")
    if skipped:
        print(f"skipped (no phonemes): {' '.join(skipped)}")


if __name__ == "__main__":
    main()
