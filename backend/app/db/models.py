from datetime import UTC, date, datetime
from uuid import UUID, uuid4

from sqlalchemy import Column, DateTime
from sqlmodel import Field, SQLModel


class Summary(SQLModel, table=True):
    """Persisted meeting summary."""

    __tablename__ = "summaries"  # type: ignore[assignment]

    id: UUID = Field(
        default_factory=uuid4,
        primary_key=True,
        description="Unique identifier of the summary",
    )
    filename: str = Field(..., max_length=255, description="Name of the uploaded audio file")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False),
        description="Timestamp when the summary was created (UTC)",
    )
    overall_summary: str = Field(..., description="Overall summary of the meeting")


class Topic(SQLModel, table=True):
    """A topic discussed in the meeting."""

    __tablename__ = "topics"  # type: ignore[assignment]

    id: int | None = Field(default=None, primary_key=True, description="Primary key")
    summary_id: UUID = Field(
        foreign_key="summaries.id",
        ondelete="CASCADE",
        index=True,
        description="FK to the parent summary",
    )
    title: str = Field(..., description="Title of the topic")
    summary: str = Field(..., description="Detailed summary of the topic")


class Decision(SQLModel, table=True):
    """A decision made during the meeting."""

    __tablename__ = "decisions"  # type: ignore[assignment]

    id: int | None = Field(default=None, primary_key=True, description="Primary key")
    summary_id: UUID = Field(
        foreign_key="summaries.id",
        ondelete="CASCADE",
        index=True,
        description="FK to the parent summary",
    )
    description: str = Field(..., description="Description of the decision")
    decided_by: str | None = Field(default=None, description="Person or group that made the decision")


class ActionItem(SQLModel, table=True):
    """An action item assigned during the meeting."""

    __tablename__ = "action_items"  # type: ignore[assignment]

    id: int | None = Field(default=None, primary_key=True, description="Primary key")
    summary_id: UUID = Field(
        foreign_key="summaries.id",
        ondelete="CASCADE",
        index=True,
        description="FK to the parent summary",
    )
    description: str = Field(..., description="Description of the action item")
    assignee: str | None = Field(default=None, description="Person responsible for the action item")
    due_date: date | None = Field(default=None, description="Due date for the action item")
