from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel.ext.asyncio.session import AsyncSession

if TYPE_CHECKING:
    import uuid

from app.db.crud import get_summary, list_summaries
from app.db.engine import get_session
from app.schema.summaries import SummaryListItem, SummaryRead

router = APIRouter(prefix="/summaries", tags=["summaries"])

Session = Annotated[AsyncSession, Depends(get_session)]


@router.get("", response_model=list[SummaryListItem])
async def list_summaries_endpoint(session: Session) -> list[SummaryListItem]:
    """Return all summaries ordered by creation date descending."""
    return await list_summaries(session)


@router.get("/{summary_id}", response_model=SummaryRead)
async def get_summary_endpoint(summary_id: uuid.UUID, session: Session) -> SummaryRead:
    """Return a single summary with full detail.

    Raises:
        HTTPException: 404 if the summary does not exist.
    """
    result = await get_summary(session, summary_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Summary not found")
    return result
