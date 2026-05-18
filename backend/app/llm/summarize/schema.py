from datetime import date

from pydantic import BaseModel, Field, field_validator


class Topic(BaseModel):
    """Represents a topic extracted from the transcript.

    Fields:
        title (str): The title of the topic.
        summary (str): A brief summary of the topic.
        segment_ids (list[int]): List of segment IDs that belong to this topic.
    """
    title: str = Field(..., description="The title of the topic", max_length=50)
    summary: str = Field(
        ...,
        description="Detailed explanation of the topic including specific statements, context, and nuance",
        max_length=2000,
    )
    segment_ids: list[int] = Field(..., description="List of segment IDs that belong to this topic")


class Decision(BaseModel):
    """Things that were decided during the meeting.

    Fields:
        description (str): A description of the decision.
        decided_by (str | None): The person or group that made the decision. Null if unknown.
        segment_ids (list[int]): List of segment IDs that relate to this decision.
    """
    description: str = Field(..., description="A description of the decision", max_length=1000)
    decided_by: str | None = Field(
        None, description="The person or group that made the decision", max_length=100,
    )
    segment_ids: list[int] = Field(..., description="List of segment IDs that relate to this decision")


class ActionItem(BaseModel):
    """Action items that were assigned during the meeting.

    Fields:
        description (str): A description of the action item.
        assignee (str | None): The person or group that is responsible for the action item. Null if unknown.
        due_date (date | None): The due date for the action item in ISO 8601 format (YYYY-MM-DD). Null if unknown.
        segment_ids (list[int]): List of segment IDs that relate to this action item.
    """
    description: str = Field(..., description="A description of the action item", max_length=1000)
    assignee: str | None = Field(
        None,
        description="The person or group that is responsible for the action item",
        max_length=100,
    )
    due_date: date | None = Field(None, description="The due date for the action item in ISO 8601 format (YYYY-MM-DD)")
    segment_ids: list[int] = Field(..., description="List of segment IDs that relate to this action item")

    @field_validator("due_date", mode="before")
    @classmethod
    def _parse_due_date(cls, value: object) -> date | None:
        """Fall back to None when the LLM returns a non-ISO date string.

        Without this, a single malformed date in one action item would raise
        ValidationError and discard the entire summary (overall_summary,
        topics, decisions, and all other action items).

        Args:
            value (object): Raw value provided by the LLM (date, str, or None).

        Returns:
            date | None: Parsed date if valid ISO 8601, otherwise None.
        """
        if value is None or isinstance(value, date):
            return value
        if isinstance(value, str):
            try:
                return date.fromisoformat(value)
            except ValueError:
                return None
        return None


class Summary(BaseModel):
    """A summary of the meeting.

    Fields:
        overall_summary (str): A brief summary of the meeting.
        topics (list[Topic]): A list of topics discussed during the meeting.
        decisions (list[Decision]): A list of decisions made during the meeting.
        action_items (list[ActionItem]): A list of action items assigned during the meeting.
    """
    overall_summary: str = Field(
        ...,
        description="A detailed description of the meeting covering the full flow and content",
        max_length=3000,
    )
    topics: list[Topic] = Field(..., description="A list of topics discussed during the meeting")
    decisions: list[Decision] = Field(..., description="A list of decisions made during the meeting")
    action_items: list[ActionItem] = Field(
        ..., description="A list of action items assigned during the meeting",
    )
