from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func
from sqlmodel import col, select

from app.db.engine import SessionDep
from app.db.models import ActionItem, Decision, Summary, Topic
from app.schema.summaries import (
    ActionItemRead,
    DecisionRead,
    SummaryListItem,
    SummaryPageResponse,
    SummaryRead,
    TopicRead,
)

router = APIRouter(prefix="/summaries", tags=["summaries"])


@router.get("")
async def list_summaries_endpoint(
    session: SessionDep,
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
        # id is a unique tiebreaker: created_at alone is not unique (rows
        # inserted in the same instant collide), and Postgres does not
        # guarantee row order on a non-unique sort key, which would let items
        # drift between pages (re-appearing or being skipped).
        .order_by(col(Summary.created_at).desc(), col(Summary.id).desc())
        .limit(limit)
        .offset(offset)
    )
    rows = (await session.exec(stmt)).all()

    if rows:
        total = int(rows[0][1])
        items = [
            SummaryListItem(
                id=summary.id,
                filename=summary.filename,
                created_at=summary.created_at,
                overall_summary=summary.overall_summary,
            )
            for summary, _ in rows
        ]
    else:
        total = (await session.exec(select(func.count()).select_from(Summary))).one()
        items = []

    return SummaryPageResponse(items=items, total=total, limit=limit, offset=offset)


@router.get("/{summary_id}")
async def get_summary_endpoint(summary_id: UUID, session: SessionDep) -> SummaryRead:
    """Return a single summary with full detail.

    Raises:
        HTTPException: 404 if the summary does not exist.
    """
    row = await session.get(Summary, summary_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Summary not found")

    # Order by id so the children come back in a stable, insertion-order
    # sequence; without an explicit ORDER BY, Postgres may return rows in any
    # order and the response ordering would vary between requests.
    topics = (
        await session.exec(
            select(Topic).where(col(Topic.summary_id) == summary_id).order_by(col(Topic.id))
        )
    ).all()
    decisions = (
        await session.exec(
            select(Decision).where(col(Decision.summary_id) == summary_id).order_by(col(Decision.id))
        )
    ).all()
    action_items = (
        await session.exec(
            select(ActionItem).where(col(ActionItem.summary_id) == summary_id).order_by(col(ActionItem.id))
        )
    ).all()

    return SummaryRead(
        id=row.id,
        filename=row.filename,
        created_at=row.created_at,
        overall_summary=row.overall_summary,
        topics=[TopicRead(title=t.title, summary=t.summary) for t in topics],
        decisions=[DecisionRead(description=d.description, decided_by=d.decided_by) for d in decisions],
        action_items=[
            ActionItemRead(description=a.description, assignee=a.assignee, due_date=a.due_date)
            for a in action_items
        ],
    )
