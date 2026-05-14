# DB Design

## ER Diagram

```mermaid
erDiagram
    summaries {
        uuid        id              PK
        text        filename
        timestamptz created_at
        text        overall_summary
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
        text    due_date    "nullable"
    }

    summaries ||--o{ topics       : "has"
    summaries ||--o{ decisions    : "has"
    summaries ||--o{ action_items : "has"
```

## 設計メモ

### `due_date` の型

`action_items.due_date` は `text` 型。LLM が "来週月曜" や "2025-06-01" のように多様な形式で返す可能性があるため、`date` 型への変換は行わない。

### CASCADE 削除

`topics` / `decisions` / `action_items` の `summary_id` FK に `ON DELETE CASCADE` を設定。`summaries` のレコードを削除すると子レコードも自動削除される。

### `created_at` のデフォルト

`default=datetime.now(UTC)` はモジュールロード時に一度だけ評価されるため、全レコードが同じ日時になるバグがある。以下に修正が必要。

```python
created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
```
