from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class _ReadModel(BaseModel):
    """Base for response models built directly from ORM rows via model_validate."""

    model_config = ConfigDict(from_attributes=True)


class TopicRead(_ReadModel):
    """Topic in a summary response."""

    title: str = Field(..., description="Title of the topic")
    summary: str = Field(..., description="Detailed summary of the topic")


class DecisionRead(_ReadModel):
    """Decision in a summary response."""

    description: str = Field(..., description="Description of the decision")
    decided_by: str | None = Field(None, description="Person or group that made the decision")


class ActionItemRead(_ReadModel):
    """Action item in a summary response."""

    description: str = Field(..., description="Description of the action item")
    assignee: str | None = Field(None, description="Person responsible for the action item")
    due_date: date | None = Field(None, description="Due date for the action item")


class SummaryListItem(_ReadModel):
    """Summary metadata for list responses."""

    id: UUID = Field(..., description="Unique identifier of the summary")
    filename: str = Field(..., description="Name of the uploaded audio file")
    created_at: datetime = Field(..., description="Timestamp when the summary was created")
    overall_summary: str = Field(..., description="Overall summary of the meeting")


class SummaryRead(SummaryListItem):
    """Full summary including all related items."""

    topics: list[TopicRead] = Field(..., description="Topics discussed in the meeting")
    decisions: list[DecisionRead] = Field(..., description="Decisions made during the meeting")
    action_items: list[ActionItemRead] = Field(..., description="Action items assigned during the meeting")


class SummaryPageResponse(BaseModel):
    """Paginated list of summaries."""

    items: list[SummaryListItem] = Field(..., description="Summaries in the current page")
    total: int = Field(..., description="Total number of summaries in the database")
    limit: int = Field(..., description="Maximum number of items returned per page")
    offset: int = Field(..., description="Number of items skipped before this page")
