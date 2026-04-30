# Kikitoru

「聞き取る」— 音声会議から議事録を自動生成する LLM ベースのアプリケーション。

## 概要

Kikitoru は会議音声を文字起こし、話者分離、LLM 要約を経て、構造化された Markdown 議事録を生成します。さらに過去の議事録を自然言語で横断検索し「あの件はどこで話されたか」を即座に呼び出せる機能を備えます。

## 開発状況

開発中。詳細な計画は [docs/PLAN.md](docs/PLAN.md) を参照。

## 主要技術

- Python 3.14、uv
- 文字起こし：Kotoba-Whisper-v2.0（日本語特化）
- 話者分離：pyannote/speaker-diarization-3.1
- 要約：Claude Sonnet（Anthropic API）
- データベース：PostgreSQL 16 + pgvector
- 推論環境：RTX 5090（CUDA）

## ディレクトリ構成

```
.
├── README.md
├── LICENSE
├── docs/
│   └── PLAN.md
└── backend/          # Python アプリケーション
    ├── pyproject.toml
    ├── .python-version
    └── main.py
```
