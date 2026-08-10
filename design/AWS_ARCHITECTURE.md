# Kikitoru AWS Architecture Design

> このドキュメントは実装判断の指針として「どの component が AWS の何を使うか」を粒度粗く決めるもの。
> 詳細 spec (VPC ID / IAM policy / IaC 詳細等) は deploy 時期に決める。

## 0. スコープ

- **対象**: prod deploy 時の component 配置決定
- **対象外**: IaC (Terraform/CDK) 詳細、VPC subnet 設計、cost 計算 (別 doc)
- **想定 region**: Tokyo (ap-northeast-1) を初期 region、**将来 multi-region 化可能な設計を保つ**
- **想定規模 (初期)**: MAU 10 以下 (`design/SCALING_ESTIMATES.md` の 1x)

## 1. 現状 component 棚卸し

| Component | 現状の実装 | AWS 化予定? |
|---|---|---|
| Backend API | FastAPI (docker-compose) | ⏳ 検討 |
| Worker | 自作 polling worker (docker-compose) | ⏳ 検討 |
| DB | PostgreSQL 18 (docker-compose) | ⏳ 検討 |
| Storage (音声/結果) | AWS S3 | ✅ 既に AWS |
| STT | AWS Transcribe | ✅ 既に AWS |
| LLM | Google Gemini (API 直) | ⏳ 検討 (Bedrock も候補) |
| Frontend | Vite React (dev server) | ⏳ 検討 |
| Auth (OAuth) | Google OAuth (自前 callback) | ⏳ 検討 (Cognito 候補) |
| Session | Postgres の user_sessions table | ⏳ 検討 |
| Queue | transcription_jobs 単一テーブル (自作 DB キュー) | ⏳ 検討 (SQS 候補) |
| CDN | 無 | ⏳ 検討 |
| Load balancer | 無 | ⏳ 検討 |
| Secrets | .env file | ⏳ 検討 (Secrets Manager) |
| Log/Metric | loguru stdout | ⏳ 検討 (CloudWatch) |

## 2. AWS mapping

各 component の [現状] [候補] [選択] [理由] [defer 事項] を記載。

### 2.0 IaC 戦略 (全 component 共通)

- **Compute 層 (backend / worker / migrate)** → **AWS Copilot** で管理
- **Data / Auth / CDN 層 (RDS / S3 / Cognito 等)** → **Terraform** で管理
- deploy 順: `terraform apply` (data 層) → `copilot deploy` (compute 層)
- Copilot addon (CloudFormation) は使わない (Terraform に集約)

### 2.1 Compute (Backend + Worker + Migrate)

**選択**: **ECS Fargate on Copilot**

| service | Copilot type | 役割 |
|---|---|---|
| backend | Load Balanced Web Service | FastAPI HTTP (ALB 自動) |
| worker | Worker Service | 自作 polling worker (background 常駐) |
| migrate | Job | alembic upgrade head (deploy 時 one-shot) |

**理由**:
- 3 service (backend / worker / migrate) を **1 tool で統一管理**
- Copilot が VPC / ALB / IAM / CloudWatch を自動生成 → boilerplate 最小
- deploy 失敗時の auto rollback
- 5 年運用実績 + community 事例豊富

**代替検討したもの**:
- ECS Express Mode: backend だけシンプル化できるが worker/migrate は別モードになり統一感が消える
- App Runner: worker (background) 非対応
- EKS: overkill (現規模 MAU < 100)
- Lambda: STT worker (最大 30 分実行) が 15 分制限に引っかかる

**Multi-region 対応**:
- Copilot は environment 単位で region 分離
- `copilot env init --name prod-ap-northeast-1` / `prod-ap-southeast-1` で dual region 可
- Route53 latency routing で ALB を region 選択

**Defer 事項**:
- CPU / memory sizing (deploy 時に負荷実測してから)
- auto-scale threshold (deploy 後にチューニング)
- CI/CD (Copilot pipeline 使うか GitHub Actions で copilot deploy 呼ぶか)

### 2.2 Database

**選択**: **RDS for PostgreSQL** (Terraform 管理)

**初期 spec**:
- Engine: PostgreSQL 18
- Instance class: `db.t4g.micro` or `db.t4g.small` (Graviton 系)
- Multi-AZ: 無 (MAU < 10 で SPOF 許容)
- Storage: gp3 20GB, auto-scale 100GB まで
- Backup: 7 日 (RDS 標準)

**理由**:
- 現行 docker Postgres と挙動一致 (pgvector / 部分 UNIQUE index / SKIP LOCKED をそのまま使える)
- cost 最小 (概算 月 15-30 USD)
- Aurora への将来移行パス残す (Postgres protocol 互換)

**Multi-region 対応**:
- Phase 1 は Tokyo 単一
- 将来 multi-region 化する時に **Aurora Global Database に移行**
- Aurora 前提の設計 (schema / query) を守っておく (`SERIAL` 等の Aurora 非互換避ける)

**Defer 事項**:
- Multi-AZ 有効化 timing (MAU 増加 or 可用性要件出た時)
- Aurora 移行 timing (Phase 2 以降)
- pgvector 使用 (Phase 1B 実装時に判断. version 依存で instance class 影響あり)
- Read replica 追加 (負荷実測後)
- Backup retention 期間 (compliance 要件次第)

### 2.3 Storage (S3) — 既存

- 現状: `S3_BUCKET` env で bucket 名指定、boto3 で put/get
- **変更なし** (既存 IAM policy は `docs/aws-setup.md` 参照)
- 将来 multi-region: CRR (Cross-Region Replication) で region 間 sync

### 2.4 STT (Transcribe) — 既存

- 現状: `AWS_REGION` env で region 指定
- **変更なし**
- 将来 multi-region: region 別に Transcribe 呼び出し (S3 も同 region に置く)

### 2.5 Auth

**選択**: **現状維持** (Google OAuth 直 + 自前 session table). **Cognito 導入は defer**.

**現状**:
- Google OAuth (自前 callback)
- `oauth_identities` table (provider + sub の pair で汎用 external identity)
- `users` table (role / status: pending/approved/rejected)
- `user_sessions` table (session token hash)
- FastAPI dependencies (`get_current_user`, `ApprovedUser`)

**Defer 理由**:
- 現状 MAU < 10 で Cognito 主要 benefit (MFA / 監査ログ / 分散) が効かない
- 移行コスト重い (session/JWT/callback/dependency 全書き換え)
- Deploy 時期未定 = 移行 timing も未定

**将来の Cognito 化に向けて今から守る設計**:
- `oauth_identities` の provider+sub 汎用表現を維持 (Cognito sub にマップ可能)
- `role` / `status` を auth backend 非依存に (Cognito group にも DB status にも切替可)
- auth dependencies (`get_current_user`, `ApprovedUser`) を隔離 (ここだけ書き換えて Cognito 化可能)

**Defer 事項** (deploy 設計時に再検討):
- Cognito 導入可否
- User pool 設計 (email + Google federation)
- Admin approval workflow の載せ方 (post-confirmation trigger or DB status 維持)
- Frontend の Cognito JS SDK 導入 vs backend で JWT 検証のみ

### 2.6 Queue

**選択**: **`transcription_jobs` 単一テーブルの自作 DB キュー on RDS** (KKT-77). polling 2 秒固定, fencing は `owner_token` (UUID).

**Phase**:
- **Phase 1 (Deploy 直後)**: 自作キュー単独. RDS 1 個で完結.
- **Phase 2 (issue #67 実装時)**: hybrid. Transcribe 完了通知だけ EventBridge → SQS で受け, 行を `pending` に戻す小さな consumer を足す. 実行本体は自作キュー維持.
- **Phase 3 (MAU 100+ or RDS が queue で圧迫)**: SQS 完全移行検討.

**KKT-66 (procrastinate) から差し戻した理由**:
- procrastinate の `finish_job` は `WHERE id = job_id` だけで行を確定させ, 自分がまだ所有者かを検証しない. 心拍の誤検出で 2 人が同じジョブを持つと, 先に抜けた側が実行中の相手のキュー行を消せる (孤児化)
- ライブラリの SQL 関数なので `AND worker_id = <自分>` を足せず, **検出して復帰させることしかできなかった** (KKT-73 / KKT-75)
- キュー行と台帳を 1 行に統合すると自分たちの SQL になり, 全更新に `AND owner_token = :token` を書ける → **孤児化というクラスごと消える**
- 副次効果: INSERT と defer を 1 tx にするための raw psycopg 取り出しが不要になり, キュー投入が INSERT 1 本になった

**構成** (`app/jobs/`):

| ファイル | 役割 |
|---|---|
| `worker.py` | N レーンの実行ループ + reclaim (60 秒) + purge (1 時間) + SIGTERM 処理 |
| `tasks.py` | 1 件の処理 (heartbeat 起動 → STT → LLM → 保存) |
| `core.py` | `transcription_jobs` への全 DB アクセス (投入・取得・完了・回収・削除) |

- 同時実行数 = レーン数 (`WORKER_CONCURRENT_LIMIT`, 既定 4). 各レーンが高々 1 件しか持たないので構造的に上限が決まる
- 取得は `FOR UPDATE SKIP LOCKED`. 複数レプリカでも二重取得しない (統合テストで検証済み)
- reclaim / purge は単文 UPDATE / DELETE なので全レプリカで同時に走らせて安全
- 停止時は `release_claims` で自分の分だけ `pending` に戻す (試行を消費しない). `stop_grace_period: 30s` が必要

**Multi-region 対応**:
- キューは RDS に依存 → **region-local**
- Multi-region 化時は region ごとに queue + worker cluster
- Cross-region job dispatch は避ける (SQS も基本 region-local)

**Defer 事項**:
- SQS 完全移行 timing (RDS 負荷監視して判断). receipt handle が fencing を構造的に与えるが, `send_message` が Postgres tx に入れないため transactional outbox が要る
- Dead letter queue 相当の実装 (`transcription_jobs.status='failed'` を監視)
- `llm_semaphore` はプロセス内カウンタなので, レプリカを増やすと実効上限が掛け算になる. 効かせたくなったら DB か Redis へ出す

### 2.7 Frontend

**選択**: **S3 + CloudFront** (Terraform 管理)

**構成**:
- Vite build → `dist/` の static files
- `dist/` を S3 bucket (`kikitoru-frontend-<env>`) に sync
- CloudFront distribution が S3 を origin として配信
- Custom domain + SSL (ACM 証明書, `us-east-1` に発行必須)
- CI/CD: GitHub Actions で `bun run build` → `aws s3 sync` → CloudFront invalidation

**理由**:
- 純 SPA (SSR 不要) なので static hosting で十分
- cost 最小 (概算 月 <5 USD)
- 他 infra が Terraform 統一されるので tool 統一感
- Amplify Hosting の便利さより Amplify エコシステム引き込みを避けたい

**Multi-region 対応**:
- CloudFront は global CDN (自動で multi-region)
- S3 origin は 1 region で OK (edge cache がグローバル配布)
- 将来 backend 側で multi-region 化する時は CloudFront の origin group で切替

**Defer 事項**:
- Custom domain (取得 timing + DNS 設計)
- Preview URL (PR ごとの deploy か. Amplify Hosting 移行 or Vercel 併用も選択肢)
- Cache-Control policy (immutable asset は 1 year, index.html は no-cache 等)
- WAF (CloudFront に WAF attach するか. 初期は不要)

### 2.8 Networking (LB, CDN, Domain, WAF)

**大半は他 section で決定済み**:

- ALB (backend): Copilot が自動生成
- VPC / Subnet / SG: Copilot が自動生成
- CloudFront (frontend): 2.7 で決定

**この section で決めるもの**:

**Custom domain**: 外部 registrar (お名前.com / Cloudflare Registrar 等) + **Route53 で DNS 管理**
- registrar は自由 (安い所で取得)
- Route53 で hosted zone 作成 → DNS record 一元管理
- IAM で DNS 変更権限を制御可能

**URL 構成**: **path-based** (シングルオリジン)
- Frontend: `kikitoru.jp/*` → S3 (CloudFront)
- Backend API: `kikitoru.jp/api/*` → ALB
- CloudFront の behavior で `/api/*` を ALB origin にルーティング
- **CORS 不要** (同一 origin), cookie 共有楽

**SSL 証明書 (ACM)**:
- CloudFront 用: **必ず `us-east-1`** に発行 (CloudFront の仕様)
- ALB 用: region-local (`ap-northeast-1`) に発行
- ただし path-based なら CloudFront のみで SSL 終端 → ALB は HTTP でも OK

**WAF**: **無し** (Phase 1)
- MAU < 10 で必要性薄い
- slowapi の rate limit で当面対応
- MAU 100+ or spam 実害出たら CloudFront に AWS WAF v2 attach

**API Gateway**: **使わない**
- ECS Fargate + ALB で十分
- 将来 Lambda function 追加 (webhook 受信等) する時に選択肢に入る

**Multi-region 対応**:
- Route53 latency-based routing で region 選択 (ALB を region 別に持ち, DNS で振分)
- CloudFront は global なので frontend は自動 multi-region
- ACM 証明書は region ごとに発行

**Defer 事項**:
- Domain 名 (取得は deploy 直前)
- Route53 health check (failover DNS 用)
- WAF 導入 timing
- ACM 証明書自動更新の監視 alarm

### 2.9 Secrets / Config

**選択**: **Secrets Manager + Parameter Store 併用**, IAM Role で AWS credential 廃止

**使い分け**:

| 対象 | 保存先 | 理由 |
|---|---|---|
| DB password | Secrets Manager | RDS 統合で auto rotation 可能 |
| OAuth client secret | Parameter Store (SecureString) | rotation 不要, 無料 |
| API keys (Gemini 等) | Parameter Store (SecureString) | 同上 |
| 通常 config (S3_BUCKET, AWS_REGION 等) | Copilot manifest.yml の env | plain text で OK |

**Copilot 統合**:

```yaml
# copilot/backend/manifest.yml
secrets:
  DATABASE_URL: /kikitoru/prod/database-url    # Secrets Manager or SSM path
  GOOGLE_API_KEY: /kikitoru/prod/google-api-key
  GOOGLE_CLIENT_SECRET: /kikitoru/prod/google-client-secret
```

Copilot が Task Role に読み取り権限を自動付与.

**AWS 認証 (IAM Role)**:

- 本番では ECS Task Role で S3/Transcribe 権限付与 → **アクセスキーを .env に置かない**
- 既存 `docs/aws-setup.md` の IAM policy を Task Role に転記
- Dev は現状の IAM ユーザー + アクセスキーのまま (docker-compose の env)

**Defer 事項**:
- Secrets Manager rotation の実装 (Lambda 書く必要)
- KMS CMK 使うか (default AWS-managed key で開始)

### 2.10 Observability (Log, Metric, Alert)

**選択**: **CloudWatch 中心 (Phase 1)** + 将来 APM/Sentry 検討

**Phase 1 構成**:

| 対象 | 実装 |
|---|---|
| Log | CloudWatch Logs (Copilot 自動 wiring). loguru → stdout → 自動収集 |
| Metric (infra) | CloudWatch Container Insights (Copilot 自動) |
| Metric (business) | 未計装. 増えたら PutMetricData で custom metric |
| Alarm | 主要 3 つのみ. CloudWatch Alarm → SNS → email |
| Cost | AWS Budgets で月次 alert (100 USD 超で email) |

**主要 alarm (Phase 1)**:

1. Backend 500 rate > 5% (5 分 window)
2. Worker task failure rate > 10% (transcription_jobs.status='failed' の割合)
3. RDS CPU > 80% (5 分 window)

**Phase 2 以降**:

- APM: OpenTelemetry (Grafana Cloud 無料枠 or Datadog)
- Error tracking: Sentry (前線の app error 拾い, 無料枠あり)
- Business metrics 計装 (job 処理数, avg 処理時間, retry 率, LLM token 消費)

**Multi-region 対応**:

- CloudWatch は region-local
- Multi-region 化時は cross-region dashboard 作成
- Grafana Cloud 等の統合 tool に集約するのが多region で楽

**Defer 事項**:
- APM 導入 timing
- Sentry 導入 timing
- Business metrics の定義 (何を測るか)
- CloudWatch dashboard の設計

## 3. データフロー図

```text
ユーザー
  │
  ▼
CloudFront (kikitoru.jp)
  ├── /*        → S3 (Frontend: Vite build)
  └── /api/*    → ALB
                  │
                  ▼
              ECS Fargate: backend (Copilot)
                  ├── (auth)    → Google OAuth callback
                  ├── (session) → RDS Postgres (user_sessions)
                  ├── (upload)  → S3 (uploads/)
                  └── (enqueue) → RDS (transcription_jobs に INSERT)
                                       │
                                       ▼ pull
                                ECS Fargate: worker (Copilot)
                                    ├── (STT) → AWS Transcribe → S3 (results/)
                                    ├── (LLM) → Google Gemini API (外部)
                                    └── (write) → RDS (summaries, segments)

On deploy:
  Terraform → RDS, S3 buckets, Cognito (将来), CloudFront, Route53, Secrets
  Copilot   → ECS cluster, ALB, ECR, backend / worker / migrate services

migrate (Copilot Job):
  RDS ← alembic upgrade head (deploy 時 one-shot)

Periodic (worker プロセス内のループ):
  worker → RDS: 孤児ジョブの回収 (60 秒間隔)
  worker → RDS + S3: 保持期間切れの削除 (1 時間間隔)
```

## 4. 実装時の指針 (今のコードに効く事項)

現時点のコード実装で守るべき事項. AWS deploy 時にスムーズにするため:

- **UTC timestamp を守る** (KKT-66 で started_at UTC 化済み. `_MEETING_TZ` は reference_date 用のみ)
- **auth dependency 隔離を維持** (Cognito 移行時に `get_current_user` / `ApprovedUser` だけ書き換え可能に)
- **`oauth_identities.provider + sub` 汎用構造を維持** (Cognito sub 対応可)
- **S3 access は IAM Role 前提** (アクセスキーへの依存を増やさない)
- **`transcription_jobs` の全更新に `AND owner_token = :token` を付ける** (これを外すと fencing が破れる)
- **`DATABASE_SSL_MODE` を明示** (settings.py で `Literal` 定義済み. 本番 compose にも env で渡す予定)
- **cross-region 依存を避ける** (multi-region 化準備. 現状 Tokyo 単一)
- **image 内に S3 credential を焼き込まない** (Dockerfile / secrets を清潔に)

## 5. Defer 項目まとめ

Deploy 時期に決めること一覧:

| Category | Item |
|---|---|
| Compute | CPU/memory sizing, auto-scale threshold, CI/CD (Copilot pipeline vs GitHub Actions) |
| Database | Multi-AZ, Aurora 移行 timing, pgvector 導入判否, Read replica, Backup retention |
| Auth | Cognito 導入判否, User pool 設計, Admin approval workflow の載せ方 |
| Queue | SQS 完全移行 timing, DLQ 相当の実装 |
| Frontend | Custom domain 取得, preview URL, Cache-Control policy, WAF 導入 |
| Networking | Domain 名, Route53 health check, WAF 導入 timing, ACM 監視 |
| Secrets | Rotation 実装, KMS CMK 使用 |
| Observability | APM 導入 timing, Sentry 導入 timing, Business metric 定義, Dashboard 設計 |
| Multi-region | Aurora Global DB 移行, region 増設, latency routing |
| Related issues | RDS role 分離 (#72), Transcribe idempotency (#73), prod SSL_MODE 明示 (#71), presigned URL (#64), EventBridge push (#67) |

## 6. 未決定事項 / 質問

(埋めながら出てくる質問をここに集約)

## 7. Multi-region 対応の設計原則

(初期 Tokyo 単一だが、将来 multi-region 化のために **今から守っておくべき原則**)

- **Stateless compute**: backend/worker がローカルディスクに state を持たない
- **Region-agnostic config**: region は env 変数から (hardcode しない)
- **UTC timestamps**: DB の timestamp は全 UTC (JST 混入禁止)
- **DB-neutral data model**: 全 ID は UUID (region-specific ID 使わない)
- **S3 key に region を埋めない**: bucket + prefix で region を表現しない
- **Async workflow は region-local**: cross-region の queue/DB を跨ぐ非同期処理は避ける

これらは **章 2 の各選択で参考にする**。
