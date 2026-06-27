# AWS セットアップ（STT: Transcribe + S3）

Kikitoru の STT は AWS Transcribe（文字起こし・話者分離）と S3（音声と結果 JSON の一時置き場）を使う。本書は **IAM 最小権限**、**S3 ライフサイクル（自動失効）**、**環境変数**をまとめる。

バケット名・リージョンは環境変数で渡す（[backend/app/settings/config.py](../backend/app/settings/config.py) の `S3_BUCKET` / `AWS_REGION`）。以下のコマンド例では次を自分の値に置き換えること:

```bash
BUCKET=kikitoru-stt-<account-id>-ap-northeast-1-an   # 自分のバケット名
REGION=ap-northeast-1
```

## 1. IAM 最小権限ポリシー

アプリの実行アイデンティティ（IAM ユーザーのアクセスキー、または ECS/EC2 の IAM ロール）に以下だけを付与する。`<BUCKET>` は実バケット名に置換。

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "TranscribeJobs",
      "Effect": "Allow",
      "Action": [
        "transcribe:StartTranscriptionJob",
        "transcribe:GetTranscriptionJob",
        "transcribe:DeleteTranscriptionJob"
      ],
      "Resource": "*"
    },
    {
      "Sid": "S3AudioAndTranscripts",
      "Effect": "Allow",
      "Action": [
        "s3:PutObject",
        "s3:GetObject",
        "s3:DeleteObject"
      ],
      "Resource": "arn:aws:s3:::<BUCKET>/*"
    }
  ]
}
```

- `transcribe:*` は ARN レベルの絞り込みに対応しないため `Resource: "*"`（アクション自体を 3 つに限定して最小化）。
- S3 はオブジェクト操作のみ（`audio/` と `transcripts/` への Put/Get/Delete）。バケット一覧やポリシー変更の権限は不要。
- **Transcribe の S3 アクセスについて**: バッチジョブは入力（`MediaFileUri`）と出力（`OutputBucketName`）に同一アカウントの S3 を使う。同一アカウント構成では上記の呼び出し元権限で動くが、クロスアカウントや厳格な構成では `DataAccessRoleArn` の指定が必要になる場合がある（[AWS ドキュメント](https://docs.aws.amazon.com/transcribe/latest/dg/security_iam_id-based-policy-examples.html) 参照）。

## 2. S3 ライフサイクル（孤児オブジェクトの自動失効）

パイプラインは正常時に音声・結果を `finally` で削除するが、プロセスのクラッシュやキャンセルで削除されず残ることがある（会議音声 = PII なので放置は望ましくない）。**ライフサイクルルールで `audio/` と `transcripts/` を一定期間後に自動削除**して保険をかける。

ジョブは通常数分〜（ポーリングのタイムアウト上限 30 分）で完了するため、1 日で十分。`lifecycle.json`:

```json
{
  "Rules": [
    {
      "ID": "expire-stt-audio",
      "Filter": { "Prefix": "audio/" },
      "Status": "Enabled",
      "Expiration": { "Days": 1 }
    },
    {
      "ID": "expire-stt-transcripts",
      "Filter": { "Prefix": "transcripts/" },
      "Status": "Enabled",
      "Expiration": { "Days": 1 }
    }
  ]
}
```

適用と確認:

```bash
aws s3api put-bucket-lifecycle-configuration \
  --bucket "$BUCKET" \
  --lifecycle-configuration file://lifecycle.json

aws s3api get-bucket-lifecycle-configuration --bucket "$BUCKET"
```

## 3. 環境変数

| 変数 | 用途 | 例 |
|---|---|---|
| `AWS_REGION` | Transcribe / S3 のリージョン（バケットと一致させる） | `ap-northeast-1` |
| `S3_BUCKET` | 音声と結果を置くバケット名 | `kikitoru-stt-<account-id>-ap-northeast-1-an` |
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | IAM ユーザー利用時の認証情報（ロール利用時は不要） | — |

詳細は [.env.example](../.env.example) / [.env.dev_example](../.env.dev_example) を参照。本番は IAM ロール（ECS task role / EC2 instance profile）を推奨し、静的キーは置かない（[docker-compose.yml](../docker-compose.yml) も同方針）。
