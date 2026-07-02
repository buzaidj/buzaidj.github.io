# Anki search index builder

Anki デッキから、サイトの単語検索（`/anki/`）で使う検索インデックスを生成する。
カードの作成・音声・ピッチアクセントは別リポジトリ
[anki-pipeline](https://github.com/buzaidj/anki-pipeline) が担当。

`build_anki_embeddings.py` を実行すると、以下が順番に生成される：

1. `build_anki_embeddings.py` — `cards.json` と意味 embeddings（e5-small / e5-base / ruri）
2. `build_reading_index.py` — `readings.json` と読み（かな）embeddings
3. `build_kana_phon_table.py` — `kana_phon.json`（音韻マッチ用テーブル）

出力はすべて `assets/anki/` に書かれる。

## 必要なもの

- **Python 3.10+**
- **Anki**（ローカルの collection.anki2 を直接読む。AnkiConnect は不要）

## 使い方

```bash
pip install -r requirements.txt
python3 build_anki_embeddings.py
```

`build_anki_embeddings.py` が終わると reading / phonetic の生成も続けて走る。

新しいカードを取り込んだ後にこれを実行すると、検索データが最新になる。
embeddings のバイナリは大きいので、履歴の肥大に注意（`updating_embeddings.txt` 参照）。
