from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class _ResponseModel(BaseModel):
    """model_validate で ORM 行から直接構築する response モデルの基底."""

    model_config = ConfigDict(from_attributes=True)


class TopicResponse(_ResponseModel):
    """要約レスポンス内の議題."""

    id: int = Field(..., description="議題の一意識別子")
    title: str = Field(..., description="議題のタイトル")
    summary: str = Field(..., description="議題の詳細な要約")


class DecisionResponse(_ResponseModel):
    """要約レスポンス内の決定事項."""

    id: int = Field(..., description="決定事項の一意識別子")
    description: str = Field(..., description="決定事項の説明")
    decided_by: str | None = Field(None, description="決定した人物またはグループ")


class ActionItemResponse(_ResponseModel):
    """要約レスポンス内のアクションアイテム."""

    id: int = Field(..., description="アクションアイテムの一意識別子")
    description: str = Field(..., description="アクションアイテムの説明")
    assignee: str | None = Field(None, description="アクションアイテムの担当者")
    due_date: date | None = Field(None, description="アクションアイテムの期限")


class SummaryListItem(_ResponseModel):
    """一覧レスポンス用の要約メタデータ."""

    id: UUID = Field(..., description="要約の一意識別子")
    filename: str = Field(..., description="アップロードされた音声ファイル名")
    created_at: datetime = Field(..., description="要約が作成された日時")
    overall_summary: str = Field(..., description="会議全体の要約")
    group_id: UUID | None = Field(
        default=None,
        description="この要約が属する要約グループのID",
    )


class SummaryResponse(SummaryListItem):
    """関連項目をすべて含む完全な要約."""

    topics: list[TopicResponse] = Field(..., description="会議で議論された議題")
    decisions: list[DecisionResponse] = Field(..., description="会議で決定された事項")
    action_items: list[ActionItemResponse] = Field(..., description="会議で割り当てられたアクションアイテム")


class SummaryPageResponse(BaseModel):
    """要約のページネーション付きリスト."""

    items: list[SummaryListItem] = Field(..., description="現在のページの要約")
    total: int = Field(..., description="データベース内の要約の総数")
    limit: int = Field(..., description="1ページあたりに返す最大件数")
    offset: int = Field(..., description="このページの前にスキップした件数")


class TranscriptSegmentResponse(_ResponseModel):
    """要約レスポンス内の文字起こしセグメント."""

    id: int = Field(..., description="セグメントの一意識別子")
    speaker_label: str = Field(..., description="話者ラベル")
    start_ms: int = Field(..., description="セグメント開始位置(ミリ秒)")
    end_ms: int = Field(..., description="セグメント終了位置(ミリ秒)")
    text: str = Field(..., description="文字起こしされたテキスト")


class SummaryGroupResponse(_ResponseModel):
    """要約グループのレスポンスモデル."""

    id: UUID = Field(..., description="要約グループの一意識別子")
    name: str = Field(..., description="要約グループの名前")
    created_at: datetime = Field(..., description="要約グループが作成された日時")


class TopicCreate(BaseModel):
    """Topicを作成するためのリクエストボディ."""

    title: str = Field(..., description="議題のタイトル")
    summary: str = Field(..., description="議題の詳細な要約")


class DecisionCreate(BaseModel):
    """Decisionを作成するためのリクエストボディ."""

    description: str = Field(..., description="決定事項の説明")
    decided_by: str | None = Field(None, description="決定した人物またはグループ")


class ActionItemCreate(BaseModel):
    """ActionItemを作成するためのリクエストボディ."""

    description: str = Field(..., description="アクションアイテムの説明")
    assignee: str | None = Field(None, description="アクションアイテムの担当者")
    due_date: date | None = Field(None, description="アクションアイテムの期限")


class TranscriptSegmentCreate(BaseModel):
    """抜けた文字起こしセグメントを作成するためのリクエストボディ."""

    speaker_label: str = Field(..., max_length=64, description="話者ラベル")
    start_ms: int = Field(..., description="このセグメントの開始時刻 (ミリ秒単位)")
    end_ms: int = Field(..., description="このセグメントの終了時刻 (ミリ秒単位)")
    text: str = Field(..., description="このセグメントの文字起こしテキスト")
    after_id: int | None = Field(
        default=None,
        description="このセグメントを挿入する位置の直前のセグメントのID. None の場合は先頭に挿入される",
    )


class SummaryGroupCreate(BaseModel):
    """SummaryGroupを作成するためのリクエストボディ."""
    name: str = Field(..., description="要約グループの名前")


class TopicEdit(BaseModel):
    """Topicを編集するためのリクエストボディ."""

    title: str | None = Field(None, description="議題のタイトル")
    summary: str | None = Field(None, description="議題の詳細な要約")


class DecisionEdit(BaseModel):
    """Decisionを編集するためのリクエストボディ."""

    description: str | None = Field(None, description="決定事項の説明")
    decided_by: str | None = Field(None, description="決定した人物またはグループ")


class ActionItemEdit(BaseModel):
    """ActionItemを編集するためのリクエストボディ."""

    description: str | None = Field(None, description="アクションアイテムの説明")
    assignee: str | None = Field(None, description="アクションアイテムの担当者")
    due_date: date | None = Field(None, description="アクションアイテムの期限")


class SummaryEdit(BaseModel):
    """Summaryを部分的に編集するためのリクエストボディ."""

    filename: str | None = Field(None, description="アップロードされた音声ファイル名")
    overall_summary: str | None = Field(None, description="会議全体の要約")
    group_id: UUID | None = Field(None, description="この要約が属する要約グループのID")


class TranscriptSegmentEdit(BaseModel):
    """TranscriptSegmentを編集するためのリクエストボディ."""

    speaker_label: str | None = Field(None, max_length=64, description="話者ラベル")
    start_ms: int | None = Field(None, description="セグメント開始位置(ミリ秒)")
    end_ms: int | None = Field(None, description="セグメント終了位置(ミリ秒)")
    text: str | None = Field(None, description="ユーザーが編集した文字起こしテキスト")


class SummaryGroupEdit(BaseModel):
    """SummaryGroupを編集するためのリクエストボディ."""
    name: str = Field(..., description="要約グループの名前")


class TranscriptSegmentSplit(BaseModel):
    """セグメントを2つに分割するためのリクエストボディ."""

    at_ms: int = Field(
        ...,
        description="分割する位置 (ミリ秒単位). セグメントの開始時刻より大きく、終了時刻より小さい必要がある"
    )
    text_before: str = Field(
        ...,
        description="分割後の前半のセグメントの文字起こしテキスト."
    )
    text_after: str = Field(
        ...,
        description="分割後の後半のセグメントの文字起こしテキスト."
    )
    speaker_before: str | None = Field(
        None,
        description="分割後の前半のセグメントの話者ラベル. None の場合は元のセグメントの話者ラベルを使用する."
    )
    speaker_after: str | None = Field(
        None,
        description="分割後の後半のセグメントの話者ラベル. None の場合は元のセグメントの話者ラベルを使用する."
    )


class TranscriptSegmentMerge(BaseModel):
    """複数セグメントを1つに結合するためのリクエストボディ."""

    speaker_label: str | None = Field(
        None,
        max_length=64,
        description="結合後のセグメントの話者ラベル. None の場合は最初のセグメントの話者ラベルを使用する."
    )
    segment_ids: list[int] = Field(
        ...,
        min_length=2,
        description="結合するセグメントのIDのリスト."
    )


class SpeakerRename(BaseModel):
    """話者ラベルを変更するためのリクエストボディ."""

    old_label: str = Field(..., max_length=64, description="変更前の話者ラベル")
    new_label: str = Field(..., max_length=64, description="変更後の話者ラベル")


class SpeakerRenameResult(BaseModel):
    """話者ラベルの変更結果を返すレスポンスモデル."""

    updated: int = Field(..., description="変更されたセグメントの数")
