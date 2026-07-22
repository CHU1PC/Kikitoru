# Kikitoru

「聞き取る」— 音声会議から議事録を自動生成する LLM ベースのアプリケーション。

## 概要

Kikitoru は会議音声を文字起こし、話者分離、LLM 要約を経て、構造化された Markdown 議事録を生成します。さらに過去の議事録を自然言語で横断検索し「あの件はどこで話されたか」を即座に呼び出せる機能を備えます。

## 開発状況

開発中。詳細な計画は [docs/PLAN.md](docs/PLAN.md) を参照。

## 主要技術

- Python 3.13、uv
- 文字起こし：AWS Transcribe（ja-JP、クラウド）
- 話者分離：AWS Transcribe の話者分離（ShowSpeakerLabels）
- 要約：Gemini（gemini-3-flash-preview / gemini-2.5-flash フォールバック、Google API）
- データベース：PostgreSQL 18（postgres:18-alpine）+ pgvector
- STT 実行環境：AWS(Transcribe + S3、ap-northeast-1).設定は [docs/aws-setup.md](docs/aws-setup.md) 参照

## ディレクトリ構成

```text
.
├── README.md
├── LICENSE
├── docker-compose.yml
├── docker-compose.dev.yml
├── docs/
│   └── PLAN.md
└── backend/          # Python アプリケーション
    ├── pyproject.toml
    ├── .python-version
    ├── main.py
    └── app/          # stt(AWS Transcribe), llm(Gemini), router, db, auth, storage(S3), settings
```

## セキュリティ

認証・認可とレート制限は実装済み。本番・非ローカル公開の前に残る確認事項もあわせて記す。

- **認証・認可：実装済み**：Google OAuth（OpenID Connect）でログインし、主要 API エンドポイント（`POST /audio/summarize`、`GET /summaries`、`GET /summaries/{id}`）は `CurrentUser` 依存で認証必須。`GET /summaries` は `Summary.user_id == user.id` でリクエストユーザーの議事録のみに絞り込み、`GET /summaries/{id}` も所有者でなければ 404 を返す（IDOR 対策済み）。
- **レート制限：実装済み**：slowapi によりクライアント IP 単位で制限（`POST /audio/summarize` は 10/hour、OAuth 系は 10/minute、超過時 429）。保存先は `RATE_LIMIT_STORAGE_URI`（既定 `memory://`、複数ワーカー時は redis 等の共有ストア推奨。[backend/app/rate_limit.py](backend/app/rate_limit.py) 参照）。
- **DB 接続の SSL（要対応）**：`DATABASE_SSL_MODE` の既定は `disable`（平文）。ネットワーク越しの接続では `verify-full` を設定すること（[backend/app/settings/config.py](backend/app/settings/config.py) 参照）。

公開前チェックリスト：ネットワーク越し DB 接続での `DATABASE_SSL_MODE=verify-full`、本番での `COOKIE_SECURE=true` と `ENABLE_DOCS=false`、複数ワーカー時に `RATE_LIMIT_STORAGE_URI` を redis 等の共有ストアへ切替。
