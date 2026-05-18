from __future__ import annotations

import asyncio
import io
import re
import unicodedata
from datetime import UTC, date, datetime
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Annotated

import magic
from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile
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
_READ_CHUNK_SIZE = 1024 * 1024  # 1 MB
_MAGIC_SNIFF_BYTES = 8192  # first 8 KiB is enough for libmagic
_MAX_FILENAME_LENGTH = 255  # matches Summary.filename column

# MIME types accepted from libmagic's content sniffing. Client-provided
# Content-Type is ignored; we trust only what the file actually looks like.
_ALLOWED_MIME_TYPES = frozenset({
    "audio/mpeg",
    "audio/mp4",
    "audio/x-m4a",
    "audio/wav",
    "audio/x-wav",
    "audio/flac",
    "audio/x-flac",
})

_CONTROL_CHAR_RE = re.compile(r"[\x00-\x1f\x7f]")
_magic_mime = magic.Magic(mime=True)


Session = Annotated[AsyncSession, Depends(get_session)]


def _sanitize_filename(filename: str | None) -> str:
    """Reduce an upload's filename to a safe, length-limited basename.

    Strips any directory components, removes control characters, normalizes
    Unicode to NFC, and caps the length so it fits in the Summary.filename
    column.

    Args:
        filename (str | None): Raw filename provided by the client.

    Returns:
        str: A safe, non-empty filename suitable for storage and display.
    """
    if not filename:
        return "unknown"
    name = PurePosixPath(filename).name  # strip path traversal segments
    name = unicodedata.normalize("NFC", name)
    name = _CONTROL_CHAR_RE.sub("", name).strip()
    if not name:
        return "unknown"
    if len(name) > _MAX_FILENAME_LENGTH:
        # Preserve the extension when truncating
        if "." in name:
            stem, _, ext = name.rpartition(".")
            ext = ext[:50]
            name = stem[: _MAX_FILENAME_LENGTH - len(ext) - 1] + "." + ext
        else:
            name = name[:_MAX_FILENAME_LENGTH]
    return name


async def _read_with_limit(file: UploadFile) -> bytes:
    """Read an UploadFile into memory while enforcing the size cap during read.

    Args:
        file (UploadFile): The incoming file.

    Returns:
        bytes: Full file contents.

    Raises:
        HTTPException: 413 if the running total exceeds _MAX_UPLOAD_BYTES.
    """
    chunks: list[bytes] = []
    total = 0
    while chunk := await file.read(_READ_CHUNK_SIZE):
        total += len(chunk)
        if total > _MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="File exceeds the 200 MB limit")
        chunks.append(chunk)
    return b"".join(chunks)


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
async def summarize_audio(
    file: UploadFile,
    session: Session,
    recorded_at: Annotated[date | None, Form()] = None,
) -> SummaryRead:
    """Accepts an audio file, summarizes it, persists the result, and returns it.

    Args:
        file (UploadFile): The audio file to process (mp3, m4a, wav, flac). Max 200 MB.
        session (AsyncSession): Database session.
        recorded_at (date | None): Date when the meeting was recorded (ISO 8601:
            YYYY-MM-DD). Used as the reference date for relative date expressions
            in the audio (e.g., "来週月曜"). Defaults to today (UTC).

    Returns:
        SummaryRead: Persisted summary including topics, decisions, and action items.

    Raises:
        HTTPException: 413 if the file exceeds 200 MB, 415 if the actual content
            is not a recognized audio format.
    """
    # Reject obvious oversized uploads before reading.
    if file.size is not None and file.size > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File exceeds the 200 MB limit")

    raw = await _read_with_limit(file)

    # Sniff the actual file content; the client-provided Content-Type is not trusted.
    detected_mime = _magic_mime.from_buffer(raw[:_MAGIC_SNIFF_BYTES])
    if detected_mime not in _ALLOWED_MIME_TYPES:
        raise HTTPException(status_code=415, detail="Unsupported audio format")

    reference_date = recorded_at or datetime.now(UTC).date()

    data = io.BytesIO(raw)
    async with pool.acquire() as (whisper, pipeline):
        segments = await asyncio.to_thread(transcribe_with_diarization, data, whisper, pipeline)
    async with llm_semaphore:
        llm_result = await summarize_chain.ainvoke((segments, reference_date))

    filename = _sanitize_filename(file.filename)
    return await _create_summary(session, filename, llm_result)
