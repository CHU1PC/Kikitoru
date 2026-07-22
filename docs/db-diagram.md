# DB Design

## ER Diagram

```mermaid
erDiagram
    users {
        uuid id PK
        text google_sub UK
        text email UK
        text name
        timestamptz created_at
        timestamptz updated_at
    }

    user_sessions {
        uuid id PK
        uuid user_id FK
        text token_hash UK
        timestamptz created_at
        timestamptz expires_at Index
        timestamptz last_seen_at
        timestamptz revoked_at "nullable"
        text user_agent "nullable"
        text ip_address "nullable"
    }

    summaries {
        uuid id PK
        uuid user_id FK
        text filename
        text content_hash
        timestamptz created_at
        text overall_summary
    }

    topics {
        serial  id          PK
        uuid    summary_id  FK
        text    title
        text    summary
    }

    decisions {
        serial  id          PK
        uuid    summary_id  FK
        text    description
        text    decided_by  "nullable"
    }

    action_items {
        serial  id          PK
        uuid    summary_id  FK
        text    description
        text    assignee    "nullable"
        date    due_date    "nullable"
    }

    users ||--o{ user_sessions : "has"
    users ||--o{ summaries : "has"
    summaries ||--o{ topics : "has"
    summaries ||--o{ decisions : "has"
    summaries ||--o{ action_items : "has"
```

## 設計メモ

### `users.google_sub`（識別子）

OIDC の `sub` claim（Subject Identifier）。Google アカウント内で**永続的かつ再割り当てされない**識別子。email は変わりうるので、これが唯一信頼できるユーザ識別子。

### `iss` は保存しない

Google は `https://accounts.google.com` と `accounts.google.com` の 2 つの iss を等価に発行する（歴史的経緯）。同一ユーザでも id_token ごとに違う iss が来る可能性があるため、保存すると同一人物を別人扱いするバグを生む。

iss は **OAuth callback での検証時のみ**チェックする（両方の値を許容）。永続化はしない。

将来マルチプロバイダ対応する時は、生の iss URL ではなく正規化した `provider` 列（"google", "github" 等）を追加するのが標準的アプローチ。

### `users.email` を unique にしない

OIDC の `email` claim は**不変ではない**:

- ユーザが Google アカウントの email を変更可能
- Gmail のエイリアス (`alice+tag@gmail.com`) が同じ実 email を指す

email は表示・通知用と割り切り、識別子としては `google_sub` のみ使う。

### `user_sessions.token_hash`（raw token は保存しない）

セッショントークン発行時に `secrets.token_urlsafe(32)` で 256bit のランダム値を生成し、その SHA-256 ハッシュを DB に保存する。raw token はクライアントの HttpOnly Cookie にしか存在しない。

検証時はクライアントから来た raw token をハッシュ化して DB と照合。**DB 漏洩時に攻撃者が盗み出したハッシュで API を叩けない**ようにするための標準的な防御（パスワードハッシュ保存と同じ発想）。

### `summaries` の複合 UNIQUE `(user_id, content_hash)`

`UNIQUE(user_id, content_hash)` にすることで:

- **同じユーザ**が同じ音声を再アップロード → 既存 summary を返す（冪等）
- **別ユーザ**が同じ音声をアップロード → 別人の summary が見えないよう、独立した summary を作成

content_hash 単独 unique にすると、最初にアップロードしたユーザの summary を別ユーザが取得できてしまう（プライバシー漏洩）。

PostgreSQL では NULL は distinct 扱いなので、`content_hash` が NULL の行は複合 unique でも衝突しない。

### `due_date` の型

`action_items.due_date` は `date` 型。LLM プロンプトで ISO 8601 形式 (YYYY-MM-DD) を強制し、確定日が不明なら `null` を返させる。

「来週月曜」のような相対表現や非 ISO 形式が返ってきた場合は、Pydantic の `field_validator` で `None` に fallback する (`app/llm/summarize/schema.py` 参照)。これにより、1件の日付パース失敗で Summary 全体がロールバックする事態を防ぐ。

### CASCADE 削除

以下の FK に `ON DELETE CASCADE` を設定:

- `user_sessions.user_id` — ユーザ削除で全セッションを自動削除
- `summaries.user_id` — ユーザ削除で所有 summary も削除
- `topics.summary_id` / `decisions.summary_id` / `action_items.summary_id` — summary 削除で子レコードも自動削除

### `created_at` のデフォルト

`default=datetime.now(UTC)` はモジュールロード時に一度だけ評価されるため、全レコードが同じ日時になるバグがある。以下に修正が必要。

```python
created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
```

### `user_session` の `revoked_at`

`revoked_at`を追加するかユーザーがログアウトした際に行を削除するかを検討したが, 不正アクセスなどの行われていないかなどのログを見るためにも`revoked_at`を追加することにした。
