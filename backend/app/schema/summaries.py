from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class _ResponseModel(BaseModel):
    """model_validate で ORM 行から直接構築する response モデルの基底."""

    model_config = ConfigDict(from_attributes=True)


class TopicResponse(_ResponseModel):
    """要約レスポンス内の議題."""

    title: str = Field(..., description="議題のタイトル")
    summary: str = Field(..., description="議題の詳細な要約")


class DecisionResponse(_ResponseModel):
    """要約レスポンス内の決定事項."""

    description: str = Field(..., description="決定事項の説明")
    decided_by: str | None = Field(None, description="決定した人物またはグループ")


class ActionItemResponse(_ResponseModel):
    """要約レスポンス内のアクションアイテム."""

    description: str = Field(..., description="アクションアイテムの説明")
    assignee: str | None = Field(None, description="アクションアイテムの担当者")
    due_date: date | None = Field(None, description="アクションアイテムの期限")


class SummaryListItem(_ResponseModel):
    """一覧レスポンス用の要約メタデータ."""

    id: UUID = Field(..., description="要約の一意識別子")
    filename: str = Field(..., description="アップロードされた音声ファイル名")
    created_at: datetime = Field(..., description="要約が作成された日時")
    overall_summary: str = Field(..., description="会議全体の要約")


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
