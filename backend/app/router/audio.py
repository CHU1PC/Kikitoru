from __future__ import annotations

import asyncio
import hashlib
import re
import tempfile
import unicodedata
from datetime import UTC, date, datetime
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Annotated

import magic
from fastapi import APIRouter, Form, HTTPException, UploadFile
from sqlalchemy.exc import IntegrityError
from sqlmodel import col, select

from app.db.engine import SessionDep  # noqa: TC001 — FastAPI resolves the dependency annotation at runtime
from app.db.models import ActionItem, Decision, Summary, Topic
from app.llm.summarize import summarize_chain
from app.router.summaries import build_summary_read
from app.schema.summaries import (
    SummaryRead,  # noqa: TC001 — FastAPI resolves the return annotation at runtime for response_model
)
from app.settings.config import llm_semaphore
from app.stt.models import pool
from app.stt.pipeline import transcribe_with_diarization

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession

    from app.llm.summarize.schema import Summary as LLMSummary
    from app.stt.types import Segment


router = APIRouter(prefix="/audio", tags=["audio"])

_MAX_UPLOAD_BYTES = 200 * 1024 * 1024  # 200 MB
_READ_CHUNK_SIZE = 1024 * 1024  # 1 MB
_SPOOL_MAX_BYTES = 8 * 1024 * 1024  # 8 MB
_MAGIC_SNIFF_BYTES = 8192
_MAX_FILENAME_LENGTH = 255


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
    name = PurePosixPath(filename).name
    name = unicodedata.normalize("NFC", name)
    name = _CONTROL_CHAR_RE.sub("", name).strip()
    if not name:
        return "unknown"
    if len(name) > _MAX_FILENAME_LENGTH:
        if "." in name:
            stem, _, ext = name.rpartition(".")
            ext = ext[:50]
            name = stem[: _MAX_FILENAME_LENGTH - len(ext) - 1] + "." + ext
        else:
            name = name[:_MAX_FILENAME_LENGTH]
    return name


async def _spool_upload(file: UploadFile) -> tuple[tempfile.SpooledTemporaryFile[bytes], str, str]:
    """Stream the upload to a spooled temp file while hashing and sniffing it.

    Reads in chunks so the whole file is never fully held in memory: small
    uploads stay in RAM, larger ones roll over to disk past _SPOOL_MAX_BYTES.
    The SHA-256 digest and the first bytes (for MIME sniffing) are computed in
    the same pass, so the content is read only once.

    Args:
        file (UploadFile): The incoming file.

    Returns:
        tuple[SpooledTemporaryFile, str, str]: The rewound temp file, the
        SHA-256 hex digest of its contents, and the libmagic-detected MIME type.

    Raises:
        HTTPException: 413 if the running total exceeds _MAX_UPLOAD_BYTES.
    """
    spooled: tempfile.SpooledTemporaryFile[bytes] = tempfile.SpooledTemporaryFile(max_size=_SPOOL_MAX_BYTES)  # noqa: SIM115
    hasher = hashlib.sha256()
    head = bytearray()
    total = 0
    while chunk := await file.read(_READ_CHUNK_SIZE):
        total += len(chunk)
        if total > _MAX_UPLOAD_BYTES:
            spooled.close()
            raise HTTPException(status_code=413, detail="File exceeds the 200 MB limit")
        hasher.update(chunk)
        if len(head) < _MAGIC_SNIFF_BYTES:
            head.extend(chunk[: _MAGIC_SNIFF_BYTES - len(head)])
        spooled.write(chunk)

    spooled.seek(0)
    detected_mime = _magic_mime.from_buffer(bytes(head))
    return spooled, hasher.hexdigest(), detected_mime


async def _transcribe(spooled: tempfile.SpooledTemporaryFile[bytes]) -> list[Segment]:
    """Run STT + diarization on the spooled upload, then release the temp file.

    Args:
        spooled (SpooledTemporaryFile): The rewound upload, owned and closed here.

    Returns:
        list[Segment]: Transcribed, speaker-labeled segments.
    """
    try:
        async with pool.acquire() as (whisper, pipeline):
            return await asyncio.to_thread(transcribe_with_diarization, spooled, whisper, pipeline)
    finally:
        spooled.close()


async def _find_by_content_hash(session: AsyncSession, content_hash: str) -> Summary | None:
    """Return the summary already stored for this audio content, or None.

    Args:
        session (AsyncSession): Database session.
        content_hash (str): SHA-256 hex digest of the uploaded audio.

    Returns:
        Summary | None: The matching summary row, or None if not yet stored.
    """
    return (
        await session.exec(select(Summary).where(col(Summary.content_hash) == content_hash))
    ).first()


async def _create_summary(
    session: AsyncSession, filename: str, content_hash: str, data: LLMSummary
) -> SummaryRead:
    """Persist a summary and its related topics, decisions, and action items.

    Args:
        session (AsyncSession): Database session.
        filename (str): Name of the uploaded audio file.
        content_hash (str): SHA-256 hex digest of the uploaded audio.
        data (LLMSummary): Structured summary from the LLM.

    Returns:
        SummaryRead: The created (or, on a content_hash race, the existing) summary.

    Raises:
        IntegrityError: If the commit fails for a reason other than a duplicate
            content_hash (the duplicate race is handled by returning the existing row).
    """
    summary = Summary(filename=filename, content_hash=content_hash, overall_summary=data.overall_summary)
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

    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        existing = await _find_by_content_hash(session, content_hash)
        if existing is not None:
            return await build_summary_read(session, existing)
        raise

    return await build_summary_read(session, summary)


@router.post("/summarize")
async def summarize_audio(
    file: UploadFile,
    session: SessionDep,
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
    if file.size is not None and file.size > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File exceeds the 200 MB limit")

    reference_date = recorded_at or datetime.now(UTC).date()
    spooled, content_hash, detected_mime = await _spool_upload(file)

    if detected_mime not in _ALLOWED_MIME_TYPES:
        spooled.close()
        raise HTTPException(status_code=415, detail="Unsupported audio format")

    existing = await _find_by_content_hash(session, content_hash)
    if existing is not None:
        spooled.close()
        return await build_summary_read(session, existing)

    segments = await _transcribe(spooled)

    async with llm_semaphore:
        llm_result = await summarize_chain.ainvoke((segments, reference_date))

    filename = _sanitize_filename(file.filename)
    return await _create_summary(session, filename, content_hash, llm_result)
