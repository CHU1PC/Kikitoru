from __future__ import annotations

import asyncio
import io
from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db.engine import get_session
from app.db.models import ActionItem, Decision, Summary, Topic
from app.llm.summarize import summarize_chain
from app.schema.summaries import ActionItemRead, DecisionRead, SummaryRead, TopicRead
from app.settings.config import llm_semaphore
from app.stt.models import pool
from app.stt.pipeline import transcribe_with_diarization

if TYPE_CHECKING:
    from app.llm.summarize.schema import Summary as LLMSummary


router = APIRouter(prefix="/audio", tags=["audio"])

_MAX_UPLOAD_BYTES = 200 * 1024 * 1024  # 200 MB
_ALLOWED_CONTENT_TYPES = frozenset({
    "audio/mpeg",
    "audio/mp4",
    "audio/wav",
    "audio/x-wav",
    "audio/flac",
    "audio/x-flac",
    "audio/m4a",
    "audio/x-m4a",
})


Session = Annotated[AsyncSession, Depends(get_session)]


async def _create_summary(session: AsyncSession, filename: str, data: LLMSummary) -> SummaryRead:
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


@router.post("/summarize")
async def summarize_audio(file: UploadFile, session: Session) -> SummaryRead:
    """Accepts an audio file, summarizes it, persists the result, and returns it.

    Args:
        file (UploadFile): The audio file to process (mp3, m4a, wav, flac). Max 200 MB.
        session (AsyncSession): Database session.

    Returns:
        SummaryRead: Persisted summary including topics, decisions, and action items.

    Raises:
        HTTPException: 413 if the file exceeds 200 MB, 415 if the format is unsupported.
    """
    if file.content_type not in _ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=415, detail=f"Unsupported media type: {file.content_type}")

    if file.size is not None and file.size > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File exceeds the 200 MB limit")

    raw = await file.read()
    if len(raw) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File exceeds the 200 MB limit")

    data = io.BytesIO(raw)
    async with pool.acquire() as (whisper, pipeline):
        segments = await asyncio.to_thread(transcribe_with_diarization, data, whisper, pipeline)
    async with llm_semaphore:
        llm_result = await summarize_chain.ainvoke(segments)

    filename = file.filename or "unknown"
    return await _create_summary(session, filename, llm_result)
