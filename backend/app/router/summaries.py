from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db.models import ActionItem, Decision, Summary, Topic
from app.dependencies import DbSessionDep
from app.schema.summaries import (
    ActionItemRead,
    DecisionRead,
    SummaryListItem,
    SummaryPageResponse,
    SummaryRead,
    TopicRead,
)

router = APIRouter(prefix="/summaries", tags=["summaries"])


async def build_summary_read(db_session: AsyncSession, summary: Summary) -> SummaryRead:
    """Load a summary's children in stable id order and assemble the read model.

    Shared by the detail endpoint and the audio router's idempotency hit so both
    return identical, deterministically-ordered payloads from the database.

    Args:
        db_session (AsyncSession): Database session.
        summary (Summary): The already-loaded parent summary row.

    Returns:
        SummaryRead: The summary with its topics, decisions, and action items.
    """
    topics = (
        await db_session.exec(
            select(Topic).where(col(Topic.summary_id) == summary.id).order_by(col(Topic.id))
        )
    ).all()
    decisions = (
        await db_session.exec(
            select(Decision).where(col(Decision.summary_id) == summary.id).order_by(col(Decision.id))
        )
    ).all()
    action_items = (
        await db_session.exec(
            select(ActionItem).where(col(ActionItem.summary_id) == summary.id).order_by(col(ActionItem.id))
        )
    ).all()

    return SummaryRead(
        id=summary.id,
        filename=summary.filename,
        created_at=summary.created_at,
        overall_summary=summary.overall_summary,
        topics=[TopicRead.model_validate(t) for t in topics],
        decisions=[DecisionRead.model_validate(d) for d in decisions],
        action_items=[ActionItemRead.model_validate(a) for a in action_items],
    )


@router.get("")
async def list_summaries_endpoint(
    db_session: DbSessionDep,
    limit: Annotated[int, Query(ge=1, le=100, description="Page size")] = 50,
    offset: Annotated[int, Query(ge=0, description="Number of items to skip")] = 0,
) -> SummaryPageResponse:
    """Return a page of summaries ordered by creation date descending.

    Uses a single query with `COUNT(*) OVER ()` so that `total` and `items`
    come from the same snapshot — avoiding the inconsistency that would
    arise if `count` and `select` were issued as separate transactions
    while concurrent inserts happen.
    """
    total_col = func.count().over().label("total")
    stmt = (
        select(Summary, total_col)
        .order_by(col(Summary.created_at).desc(), col(Summary.id).desc())
        .limit(limit)
        .offset(offset)
    )
    rows = (await db_session.exec(stmt)).all()

    if rows:
        total = int(rows[0][1])
        items = [SummaryListItem.model_validate(summary) for summary, _ in rows]
    else:
        total = (await db_session.exec(select(func.count()).select_from(Summary))).one()
        items = []

    return SummaryPageResponse(items=items, total=total, limit=limit, offset=offset)


@router.get("/{summary_id}")
async def get_summary_endpoint(summary_id: UUID, db_session: DbSessionDep) -> SummaryRead:
    """Return a single summary with full detail.

    Raises:
        HTTPException: 404 if the summary does not exist.
    """
    row = await db_session.get(Summary, summary_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Summary not found")

    return await build_summary_read(db_session, row)
