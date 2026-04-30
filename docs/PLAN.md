# Kikitoru — 開発計画 v1

## 概要

Kikitoru（聞き取る）は、会議音声から議事録を自動生成する LLM ベースのアプリケーション。

- **入力**：音声ファイル（MVP）→ リアルタイム録音（Phase 1C）
- **処理**：自動文字起こし + 話者分離 + LLM による構造化要約
- **出力**：Markdown 形式の構造化議事録
- **検索**：過去の議事録を自然言語で横断検索し「どこで何が話されたか」を呼び出せる

主要な特長：

- **日本語特化**：Kotoba-Whisper-v2.0 で日本語 ASR の最高精度を狙う
- **ローカル実行**：音声・文字起こしは RTX 5090（CUDA）上で完結。プライバシー重視
- **検証可能**：文字起こしテキストが残るので、LLM の要約を逐次検証できる
- **音声直接 LLM は使わない**：検証可能性・コスト・検索の都合から、文字起こし → テキスト LLM の二段構成

---

## アーキテクチャ原則

- **抽象化は 2 つ目の実装が出てから**：プラグインインターフェースは最初から作らない
- **重量級フレームワークを避ける**：Phase 1 では LangGraph 等を使わず、単純な関数チェーンで構成
- **DB が source of truth**：Markdown 出力は派生物
- **段階的な抽象化**：必要になった時点でリファクタする
- **テキストが central**：音声直接 LLM ではなく、文字起こしを介してすべてのダウンストリーム処理（要約・検索）を行う

---

## Phase 1A：MVP（音声ファイル → Markdown 議事録）

**目標**：音声ファイル → 文字起こし → LLM 要約 → Markdown 出力 が CLI で動く。

### 機能

- 音声ファイル（mp3 / m4a / wav / flac）を入力
- 文字起こし + 話者分離パイプライン：
  - **デフォルト STT**：Kotoba-Whisper-v2.0（日本語特化、CTranslate2 バックエンド）
  - **多言語フォールバック**：Whisper large-v3
  - **話者分離**：pyannote/speaker-diarization-3.1
- Claude Sonnet で構造化要約（JSON Schema 制約付き）：
  - 全体要約
  - 議題ごとの要約
  - 決定事項（誰が何を決めたか）
  - アクションアイテム（担当者・期日付き）
  - キーワード抽出
- 参加者リストを CLI 引数で渡せる（LLM が「Speaker 0 = 田中」のように紐付け）
- 自己紹介を含む音声では LLM が文脈推論で実名を当てる
- Markdown テンプレートで議事録ファイルを生成
- 文字起こしと要約結果を DB に保存

### Eval Harness（必須成果物）

- 模擬会議の音声フィクスチャ 5–10 件
- 各音声に対する期待される構造化要約（JSON）
- 評価指標：
  - 文字起こし WER（参考値）
  - 決定事項の抽出精度（手動採点）
  - アクションアイテムの抽出精度（手動採点）
  - 構造化出力の必須フィールド欠損率
  - LLM-as-judge による要約品質スコア

### Prompt Caching

- システムプロンプト + JSON Schema をキャッシュ
- 同一会議の異なる議題部分を要約する際にキャッシュヒット
- コスト 80–90% 削減

---

## Phase 1B：横断検索（自然言語による議事録検索）

**目標**：「あの件はどこで話されたか」が自然言語クエリで呼び出せる。

### 機能

- 過去の文字起こしと要約をハイブリッド検索：
  - **意味検索**：pgvector による埋め込み検索
  - **全文検索**：PostgreSQL の全文検索（日本語形態素解析対応）
- LLM（Claude Sonnet）が検索結果を統合して回答（RAG）
- 回答に「いつの会議のどこで話されたか」のリンク（タイムスタンプ + 会議 ID）を含める

### 埋め込み戦略

- 文字起こしを論理セグメント（話者ターン or 一定時間ごと）に分割
- セグメントごとに埋め込みを生成
- メタデータ：会議 ID、話者、開始/終了時刻

### 埋め込みモデル

- **multilingual-e5-large** または **BGE-M3**（日本語含む多言語対応）
- ローカル実行（5090 で完結）

### 日本語全文検索

- PostgreSQL 単体では日本語形態素解析が弱い
- 候補：
  - **pgroonga**（mecab 内蔵、日本語 FTS で実績多数）
  - PostgreSQL の `pg_trgm` + 文字 N-gram（簡易）
  - 全文検索を諦めて意味検索に一本化（最もシンプル）
- Phase 1B 着手時に必要性を評価して決定

---

## Phase 1C：リアルタイム録音

**目標**：マイク入力をリアルタイム文字起こしし、会議終了時に Phase 1A の要約パイプラインが自動起動。

### 機能

- `sounddevice` でマイク入力をキャプチャ
- VAD（webrtcvad or silero-vad）で音声区間検出 + チャンク化
- ストリーミング Whisper（whisper-streaming or 自前実装）で逐次文字起こし
- リアルタイム表示（CLI または最小 UI）
- 録音停止 → 自動で Phase 1A の要約パイプラインを起動

### 課題

- 話者分離はストリーミング向きではない（pyannote はバッチ前提）
- 暫定対応：リアルタイム中は話者分離なし、終了後にバッチで diarization を再走

---

## Phase 2：議事録機能の強化

- **編集 UI**：Streamlit で文字起こし・要約を編集可能に
- **エクスポート**：Markdown に加えて PDF、HTML、Notion 互換フォーマット
- **声紋登録**：過去の会議で「Speaker 0 = 田中」と確定したら、声紋データとして保存
- **声紋による自動話者特定**：次回以降の会議で声紋マッチングで自動ラベリング
- **多言語混在対応**：日本語ベースに英語の技術用語が混ざる場合の精度向上
- **長時間音声対応**：2 時間超のチャンク処理戦略
- **固有名詞辞書**：会社名・プロジェクト名・人名を CLI で渡し、Whisper のホットワード機能で精度向上

---

## Phase 3：拡張連携

- **カレンダー連携**：Google Calendar の会議イベントと録音を自動紐付け
- **アクションアイテムの外部出力**：抽出したアクションを Linear / Calendar に流す
- **共有機能**：議事録を Slack / Email で配信
- **音声直接 LLM のセカンドパス**：必要に応じて Gemini で感情ハイライトや非言語情報を追加抽出（オプション）

---

## STT パイプライン詳細

```
音声ファイル
   ↓ Kotoba-Whisper-v2.0（CTranslate2、CUDA）
文字起こし（タイムスタンプ + セグメント）
   +
   ↓ pyannote/speaker-diarization-3.1（CUDA）
話者ラベル（Speaker 0/1/2...）
   ↓ アライン（時刻ベースで結合）
文字起こし（タイムスタンプ + 話者ラベル + テキスト）
   ↓ Claude Sonnet（参加者リスト + 自己紹介から実名推論、prompt caching）
構造化要約（JSON）
   ↓ Markdown テンプレート
議事録ファイル
```

---

## タイムゾーン処理

- 録音時刻は **UTC で DB 保存**
- 表示時にユーザー TZ（IANA 表記、設定ファイル）で変換
- 議事録 Markdown には ローカル時刻 + TZ を併記
- Whisper のセグメント時刻は録音開始からの相対秒なので変換不要

---

## データモデル

```python
class Meeting(SQLModel, table=True):
    id: UUID
    title: str
    recorded_at_utc: datetime
    timezone: str               # IANA（例: "Asia/Tokyo"）
    audio_path: str | None      # ローカル音声ファイル絶対パス（DB には音声本体を保存しない）
    duration_seconds: int
    language: str               # ISO 639-1（例: "ja"）
    participants: list[str]     # 手動入力した参加者名（JSON 列）
    created_at: datetime
    updated_at: datetime


class TranscriptSegment(SQLModel, table=True):
    id: UUID
    meeting_id: UUID            # FK
    start_seconds: float
    end_seconds: float
    speaker_label: str          # "Speaker 0" or 実名
    text: str
    embedding: list[float] | None  # pgvector
    created_at: datetime


class Summary(SQLModel, table=True):
    id: UUID
    meeting_id: UUID            # FK
    overall_summary: str
    topics: str                 # JSON: [{title, summary, segment_ids: [...]}]
    decisions: str              # JSON: [{text, decided_by, segment_id}]
    action_items: str           # JSON: [{text, assignee, due_date, segment_id}]
    keywords: str               # JSON: [str]
    llm_model: str
    created_at: datetime
```

---

## 技術スタック

| レイヤー | 技術 | 選定理由 |
|--------|------|--------|
| 言語 | Python 3.14 | 現行安定版（2025-10 リリース）|
| パッケージ管理 | uv | 高速、ロックファイル |
| STT 主モデル | Kotoba-Whisper-v2.0 | 日本語 SOTA、5090 で十分速い |
| STT フォールバック | Whisper large-v3 | 多言語混在時 |
| STT バックエンド | faster-whisper / WhisperX | CTranslate2 で高速、CUDA |
| 話者分離 | pyannote/speaker-diarization-3.1 | OSS SOTA |
| LLM 要約 | Claude Sonnet | 構造化出力安定、prompt caching |
| LLM 軽量タスク | Claude Haiku | 分類・前処理用、コスト最適化 |
| DB | PostgreSQL 16 | tsvector + pgvector で hybrid 検索 |
| ORM | SQLModel + SQLAlchemy | 型 + Pydantic 統合 |
| マイグレーション | Alembic | `target_metadata = SQLModel.metadata` |
| ベクトル検索 | pgvector | hybrid search 対応 |
| 全文検索（要評価）| pgroonga or pg_trgm | 日本語形態素解析、Phase 1B で決定 |
| 埋め込みモデル | multilingual-e5-large or BGE-M3 | 日本語含む多言語、ローカル実行 |
| 録音（Phase 1C）| sounddevice + webrtcvad / silero-vad | マイクキャプチャ + VAD |
| ダッシュボード | Streamlit（Phase 2 以降）| プロトタイプ高速 |
| トークン保存 | keyring（OS キーチェーン）| Anthropic API key、HF token |
| 構造化ログ | structlog | JSON 出力 |
| 推論環境 | RTX 5090（CUDA 12.8+）| 32GB VRAM、Mac 対応は不要 |

---

## API キー / トークン管理

Phase 1 で必要な認証情報：

- **Anthropic API Key**：Claude 要約用
- **Hugging Face Token**：pyannote モデルのダウンロード（無料、利用同意のみ必要）

両方とも `keyring` で OS キーチェーン保存。デプロイ時のみ環境変数 / Secrets Manager に切り替え。

---

## 観測性

- LLM 呼び出しのレイテンシ・トークン使用量・キャッシュヒット率を記録
- STT 処理時間（モデルロード / 推論 / diarization 別）を記録
- 失敗イベント（GPU OOM、API エラー、HF token 切れ）は email 通知
- 月次の API コストレポートを自分宛てに送信

---

## デプロイ

ローカル実行が前提（RTX 5090 マシン上）：

- `uv run kikitoru transcribe path/to/audio.mp3`
- `uv run kikitoru search "プロジェクト X の決定事項"`
- DB は Docker Compose で PostgreSQL + pgvector 起動

将来的に Web UI（Streamlit）が欲しくなった場合：

- 同じマシン上で `uv run streamlit run dashboard.py`
- 外出先からアクセスしたければ Tailscale 経由 or VPN

クラウド展開は基本想定しない（音声を外に出さない方針のため）。

---

## マイルストーン

| マイルストーン | 完了条件 |
|--------------|--------|
| Phase 1A | 音声ファイル → Markdown 議事録が CLI で生成できる。Eval Harness 通過（決定事項抽出精度 ≥ 80%、アクションアイテム抽出精度 ≥ 75%） |
| Phase 1B | 過去の議事録から自然言語検索ができる。RAG 回答が引用元タイムスタンプを含む |
| Phase 1C | マイク録音 → リアルタイム文字起こし → 終了で要約パイプライン自動起動 |
| Phase 2 | 編集 UI、PDF エクスポート、声紋登録による自動話者ラベリング |
| Phase 3 | カレンダー連携、外部ツールへの出力 |

---

## リスクと対策

| リスク | 影響 | 対策 |
|------|------|------|
| 音声認識精度（特に固有名詞・専門用語）| 議事録の品質低下 | Eval Harness で監視。Phase 2 で固有名詞辞書（Whisper hotwords）対応 |
| 話者分離の誤分割（同じ人が複数 Speaker 扱い）| 議事録の混乱 | LLM に「同一人物の可能性が高い Speaker をマージ」させる前処理を入れる |
| 長時間音声のメモリ | OOM | チャンク処理（30 分単位）+ 結果結合 |
| LLM コスト膨張 | 想定外の請求 | Prompt caching、要約は Sonnet・分類は Haiku、月次モニタリング |
| LLM の要約幻覚 | 決定事項の捏造 | 文字起こしの引用必須化（segment_id を必須フィールドに） |
| 個人会議の機密性 | プライバシー懸念 | ローカル STT、音声ファイルは DB に保存しない（パスのみ） |
| pyannote のモデル利用同意 | セットアップで詰まる | README に手順記載、HF token は keyring 保存 |
| GPU OOM（複数モデル同時ロード）| 推論失敗 | モデルアンロード戦略、fp16 / int8 量子化の検討 |
| 日本語全文検索の精度 | Phase 1B の検索品質低下 | 着手時に pgroonga vs 意味検索一本化を比較評価 |
| 環境再現性 | 別マシンで動かない | uv lock、CUDA バージョン明記、HF モデルバージョン固定 |
| RTX 5090 / Blackwell の CUDA 対応 | torch / CTranslate2 が動かない | CUDA 12.8+、PyTorch nightly or 対応版を確認 |

---

## はじめに（Phase 1A セットアップ手順）

1. Python 3.14 環境（`uv sync`）
2. CUDA 12.8+ + cuDNN（RTX 5090 / Blackwell 対応版）
3. `docker compose up -d` で PostgreSQL 16 + pgvector 起動
4. Hugging Face アカウントで pyannote モデル利用同意 → token 発行 → `keyring` 保存
5. Anthropic API Key を `keyring` 保存
6. SQLModel スキーマ + Alembic 初期マイグレーション
7. Eval Harness のフィクスチャ作成（5 件、自分の過去会議 or 模擬音声）
8. STT パイプラインの実装（Kotoba-Whisper + pyannote）
9. 要約パイプラインの実装（Claude Sonnet + JSON Schema + prompt caching）
10. Markdown テンプレートの作成
11. Eval Harness で初回評価
12. CLI で End-to-end テスト
