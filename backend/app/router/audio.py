from __future__ import annotations

import asyncio
import io
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db.crud import create_summary
from app.db.engine import get_session
from app.llm.summarize import summarize_chain
from app.schema.summaries import SummaryRead
from app.settings.config import llm_semaphore
from app.stt.models import pool
from app.stt.pipeline import transcribe_with_diarization

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


@router.post("/summarize", response_model=SummaryRead)
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
    return await create_summary(session, filename, llm_result)
