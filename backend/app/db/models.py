import uuid
from datetime import UTC, date, datetime

from sqlmodel import Field, SQLModel


class Summary(SQLModel, table=True):
    """Persisted meeting summary."""

    __tablename__ = "summaries"  # type: ignore[assignment]

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    filename: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    overall_summary: str


class Topic(SQLModel, table=True):
    """A topic discussed in the meeting."""

    __tablename__ = "topics"  # type: ignore[assignment]

    id: int | None = Field(default=None, primary_key=True)
    summary_id: uuid.UUID = Field(foreign_key="summaries.id", ondelete="CASCADE")
    title: str
    summary: str


class Decision(SQLModel, table=True):
    """A decision made during the meeting."""

    __tablename__ = "decisions"  # type: ignore[assignment]

    id: int | None = Field(default=None, primary_key=True)
    summary_id: uuid.UUID = Field(foreign_key="summaries.id", ondelete="CASCADE")
    description: str
    decided_by: str | None = None


class ActionItem(SQLModel, table=True):
    """An action item assigned during the meeting."""

    __tablename__ = "action_items"  # type: ignore[assignment]

    id: int | None = Field(default=None, primary_key=True)
    summary_id: uuid.UUID = Field(foreign_key="summaries.id", ondelete="CASCADE")
    description: str
    assignee: str | None = None
    due_date: date | None = None
