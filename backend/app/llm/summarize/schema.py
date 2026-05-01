from pydantic import BaseModel, Field


class Topic(BaseModel):
    """Represents a topic extracted from the transcript."""
    title: str = Field(..., description="The title of the topic", max_length=50)
    summary: str = Field(..., description="A brief summary of the topic", max_length=400)
    segment_ids: list[int] = Field(..., description="List of segment IDs that belong to this topic")


class Decision(BaseModel):
    """Things that were decided during the meeting."""
    description: str = Field(..., description="A description of the decision", max_length=200)
    decided_by: str | None = Field(None, description="The person or group that made the decision")
    segment_ids: list[int] = Field(..., description="List of segment IDs that relate to this decision")


class ActionItem(BaseModel):
    """Action items that were assigned during the meeting."""
    description: str = Field(..., description="A description of the action item", max_length=200)
    assignee: str | None = Field(None, description="The person or group that is responsible for the action item")
    due_date: str | None = Field(None, description="The due date for the action item")
    segment_ids: list[int] = Field(..., description="List of segment IDs that relate to this action item")


class Summary(BaseModel):
    """A summary of the meeting."""
    overall_summary: str = Field(..., description="A brief summary of the meeting", max_length=1000)
    topics: list[Topic] = Field(..., description="A list of topics discussed during the meeting")
    decisions: list[Decision] = Field(..., description="A list of decisions made during the meeting")
    action_items: list[ActionItem] = Field(..., description="A list of action items assigned during the meeting")
