from __future__ import annotations

from typing import TYPE_CHECKING

from sqlmodel import col, select

from app.db.models import ActionItem, Decision, Summary, Topic
from app.schema.summaries import ActionItemRead, DecisionRead, SummaryListItem, SummaryRead, TopicRead

if TYPE_CHECKING:
    import uuid

    from sqlmodel.ext.asyncio.session import AsyncSession

    from app.llm.summarize.schema import Summary as LLMSummary


async def create_summary(session: AsyncSession, filename: str, data: LLMSummary) -> SummaryRead:
    """Persist a summary and its related topics, decisions, and action items.

    Args:
        session (AsyncSession): Database session.
        filename (str): Name of the uploaded audio file.
        data (LLMSummary): Structured summary from the LLM.

    Returns:
        SummaryRead: The newly created summary with all related items.
    """
    summary = Summary(filename=filename, overall_summary=data.overall_summary)
    session.add(summary)
    await session.flush()

    for t in data.topics:
        session.add(Topic(summary_id=summary.id, title=t.title, summary=t.summary))
    for d in data.decisions:
        session.add(Decision(summary_id=summary.id, description=d.description, decided_by=d.decided_by))
    for action_item in data.action_items:
        session.add(
            ActionItem(
                summary_id=summary.id,
                description=action_item.description,
                assignee=action_item.assignee,
                due_date=action_item.due_date,
            )
        )

    await session.commit()
    await session.refresh(summary)

    return SummaryRead(
        id=summary.id,
        filename=summary.filename,
        created_at=summary.created_at,
        overall_summary=summary.overall_summary,
        topics=[TopicRead(title=t.title, summary=t.summary) for t in data.topics],
        decisions=[DecisionRead(description=d.description, decided_by=d.decided_by) for d in data.decisions],
        action_items=[
            ActionItemRead(description=a.description, assignee=a.assignee, due_date=a.due_date)
            for a in data.action_items
        ],
    )


async def get_summary(session: AsyncSession, summary_id: uuid.UUID) -> SummaryRead | None:
    """Fetch a summary with all related items by ID.

    Args:
        session (AsyncSession): Database session.
        summary_id (uuid.UUID): The summary's primary key.

    Returns:
        SummaryRead | None: Full summary data, or None if not found.
    """
    row = await session.get(Summary, summary_id)
    if row is None:
        return None

    topics = (await session.exec(select(Topic).where(col(Topic.summary_id) == summary_id))).all()
    decisions = (await session.exec(select(Decision).where(col(Decision.summary_id) == summary_id))).all()
    action_items = (await session.exec(select(ActionItem).where(col(ActionItem.summary_id) == summary_id))).all()

    return SummaryRead(
        id=row.id,
        filename=row.filename,
        created_at=row.created_at,
        overall_summary=row.overall_summary,
        topics=[TopicRead(title=t.title, summary=t.summary) for t in topics],
        decisions=[DecisionRead(description=d.description, decided_by=d.decided_by) for d in decisions],
        action_items=[
            ActionItemRead(
                description=action_item.description, assignee=action_item.assignee, due_date=action_item.due_date
            ) for action_item in action_items
        ],
    )


async def list_summaries(session: AsyncSession) -> list[SummaryListItem]:
    """Fetch all summaries ordered by creation date descending.

    Args:
        session (AsyncSession): Database session.

    Returns:
        list[SummaryListItem]: List of summary metadata.
    """
    rows = (
        await session.exec(select(Summary).order_by(col(Summary.created_at).desc()))
    ).all()

    return [
        SummaryListItem(id=r.id, filename=r.filename, created_at=r.created_at, overall_summary=r.overall_summary)
        for r in rows
    ]
