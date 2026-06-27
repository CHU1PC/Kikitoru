from datetime import date, datetime

from loguru import logger
from pydantic import BaseModel, Field, field_validator


class Topic(BaseModel):
    """文字起こしから抽出された議題を表す."""
    title: str = Field(..., description="議題のタイトル", max_length=50)
    summary: str = Field(
        ...,
        description="具体的な発言・文脈・ニュアンスを含む、議題の詳細な説明",
        max_length=2000,
    )
    segment_ids: list[int] = Field(..., description="この議題に属するセグメント ID のリスト")


class Decision(BaseModel):
    """会議中に決定された事項."""
    description: str = Field(..., description="決定事項の説明", max_length=1000)
    decided_by: str | None = Field(
        None, description="決定した人物またはグループ", max_length=100,
    )
    segment_ids: list[int] = Field(..., description="この決定に関連するセグメント ID のリスト")


class ActionItem(BaseModel):
    """会議中に割り当てられたアクションアイテム."""
    description: str = Field(..., description="アクションアイテムの説明", max_length=1000)
    assignee: str | None = Field(
        None,
        description="アクションアイテムを担当する人物またはグループ",
        max_length=100,
    )
    due_date: date | None = Field(None, description="ISO 8601 形式 (YYYY-MM-DD) のアクションアイテムの期限")
    segment_ids: list[int] = Field(..., description="このアクションアイテムに関連するセグメント ID のリスト")

    @field_validator("due_date", mode="before")
    @classmethod
    def _parse_due_date(cls, value: object) -> date | None:
        """LLM が ISO でない日付文字列を返した場合に None にフォールバックする.

        これが無いと、1つのアクションアイテムの不正な日付1個で ValidationError が発生し、
        要約全体 (overall_summary, topics, decisions, 他の全アクションアイテム) が破棄される.
        パース失敗はログに残し、サイレントな欠落を可視化する.

        Args:
            value (object): LLM から渡された生の値 (date, datetime, str, None のいずれか).

        Returns:
            date | None: 有効な ISO 8601 ならパースした日付、そうでなければ None.
        """
        if value is None:
            return value
        if isinstance(value, date):
            return value.date() if isinstance(value, datetime) else value
        if isinstance(value, str):
            try:
                return date.fromisoformat(value)
            except ValueError:
                pass
            try:
                return datetime.fromisoformat(value).date()
            except ValueError:
                logger.warning("Discarding unparseable due_date from LLM: {!r}", value)
                return None
        logger.warning("Discarding due_date of unexpected type {}: {!r}", type(value).__name__, value)
        return None


class Summary(BaseModel):
    """会議の要約."""
    overall_summary: str = Field(
        ...,
        description="会議全体の流れと内容を網羅した詳細な説明",
        max_length=3000,
    )
    topics: list[Topic] = Field(..., description="会議で議論された議題のリスト")
    decisions: list[Decision] = Field(..., description="会議で決定された事項のリスト")
    action_items: list[ActionItem] = Field(
        ..., description="会議で割り当てられたアクションアイテムのリスト",
    )
