# Anki Japanese Card Pipeline

Google Keep に書き溜めた日本語の単語を Anki カードにして、音声・ピッチアクセント・
ふりがなを自動で付ける。さらにサイト用の検索インデックス（embeddings）を生成する。

`anki-update` を一発走らせると、以下が順番に実行される：

1. `import_from_keep.py` — Keep の「ことば」ノートを読んで Anki にカード追加（ふりがなは Claude が生成）
2. `populate_audio_with_bold.py` — Forvo から単語音声を取得
3. `populate_pitch_accent.py` — kanjium 辞書からピッチアクセントを付与
4. `build_anki_embeddings.py` — 検索用 embeddings + 読み + 音韻インデックスを生成

## 必要なもの

- **Python 3.10+**
- **Anki** + [AnkiConnect アドオン](https://ankiweb.net/shared/info/2055492159)（起動中であること）
- **Claude CLI**（`import_from_keep.py` のふりがな生成に使用）— インストールしてログイン済みであること
- **kanjium のアクセント辞書**（`kanjium_accents.txt`）— [ここ](https://github.com/mifunetoshiro/kanjium) からDL
- Anki に **「発見した言葉」ノートタイプ**（フィールド: Word, Meaning, Word furigana, Sentence, Sentence furigana, Audio, Pitch Accent）

## セットアップ

```bash
pip install -r requirements.txt
cp .env.example .env
# .env を自分の値で埋める（下記参照）
```

### .env の中身

| 変数 | 説明 |
|---|---|
| `KEEP_EMAIL` | Google アカウントのメールアドレス |
| `KEEP_MASTER_TOKEN` | Google Keep のマスタートークン（[gpsoauth](https://github.com/simon-weber/gpsoauth) で取得） |
| `FORVO_API_KEY` | [Forvo API](https://api.forvo.com/) のキー |
| `ACCENTS_FILE` | kanjium 辞書ファイルのパス（デフォルト `~/Downloads/kanjium_accents.txt`） |
| `ANKI_MEDIA_DIR` | Anki の collection.media パス（プロファイル名が違う場合は変更） |

## Keep ノートのフォーマット

「ことば」で始まるノートに、1エントリを空行区切りで書く：

```
単語
意味
例文（任意。なければ「例文なし」）
```

## 実行

```bash
python3 import_from_keep.py        # カード追加のみ

# または全部まとめて（embeddings 再生成まで）:
python3 import_from_keep.py && \
  python3 populate_audio_with_bold.py && \
  python3 populate_pitch_accent.py && \
  python3 build_anki_embeddings.py
```
