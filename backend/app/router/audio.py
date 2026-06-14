from __future__ import annotations

import asyncio
import hashlib
import re
import tempfile
import unicodedata
from datetime import date, datetime
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Annotated
from zoneinfo import ZoneInfo

import magic
from fastapi import APIRouter, Form, HTTPException, UploadFile
from sqlalchemy.exc import IntegrityError
from sqlmodel import col, select

from app.db.engine import DbSessionDep  # noqa: TC001 — FastAPI resolves the dependency annotation at runtime
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
    from uuid import UUID

    from sqlmodel.ext.asyncio.session import AsyncSession

    from app.llm.summarize.schema import Summary as LLMSummary
    from app.stt.types import Segment


router = APIRouter(prefix="/audio", tags=["audio"])

_MAX_UPLOAD_BYTES = 200 * 1024 * 1024  # 200 MB
_READ_CHUNK_SIZE = 1024 * 1024  # 1 MB
_SPOOL_MAX_BYTES = 8 * 1024 * 1024  # 8 MB
_MAGIC_SNIFF_BYTES = 8192
_MAX_FILENAME_LENGTH = 255
_MEETING_TZ = ZoneInfo("Asia/Tokyo")  # default tz when the client omits recorded_at


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
    """アップロードを spooled 一時ファイルに書き出しつつ、ハッシュ化と MIME 判定を同じ走査で行う.

    チャンク単位で読み、ファイル全体をメモリに保持しない. 小さいアップロードはメモリ上に残り、
    _SPOOL_MAX_BYTES を超えるとディスクに退避する. SHA-256 ダイジェストと先頭バイト
    (MIME sniff 用) を同じ1回の走査で計算するため、内容は1度しか読まない.

    Args:
        file (UploadFile): 受信したファイル.

    Returns:
        tuple[SpooledTemporaryFile, str, str]: 先頭に巻き戻した一時ファイル、その内容の
            SHA-256 hex ダイジェスト、libmagic が判定した MIME タイプ.

    Raises:
        HTTPException: 累積サイズが _MAX_UPLOAD_BYTES を超えた場合は 413.
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


async def _transcribe(spooled: tempfile.SpooledTemporaryFile[bytes], num_speakers: int | None = None) -> list[Segment]:
    """Run STT + diarization on the spooled upload, then release the temp file.

    Args:
        spooled (SpooledTemporaryFile): The rewound upload, owned and closed here.
        num_speakers (int | None): Optional number of speakers to detect. If None, the pipeline will
            determine the number of speakers automatically.

    Returns:
        list[Segment]: Transcribed, speaker-labeled segments.
    """
    try:
        async with pool.acquire() as (whisper, pipeline):
            return await asyncio.to_thread(transcribe_with_diarization, spooled, whisper, pipeline, num_speakers)
    finally:
        spooled.close()


async def _find_by_content_hash(db_session: AsyncSession, content_hash: str) -> Summary | None:
    """Return the summary already stored for this audio content, or None.

    Args:
        db_session (AsyncSession): Database session.
        content_hash (str): SHA-256 hex digest of the uploaded audio.

    Returns:
        Summary | None: The matching summary row, or None if not yet stored.
    """
    return (
        await db_session.exec(select(Summary).where(col(Summary.content_hash) == content_hash))
    ).first()


def _add_children(db_session: AsyncSession, summary_id: UUID, data: LLMSummary) -> None:
    """Stage the summary's topics, decisions, and action items for insert.

    Args:
        db_session (AsyncSession): Database session.
        summary_id (UUID): Parent summary id (set after flush).
        data (LLMSummary): Structured summary from the LLM.
    """
    for t in data.topics:
        db_session.add(Topic(summary_id=summary_id, title=t.title, summary=t.summary))
    for d in data.decisions:
        db_session.add(Decision(summary_id=summary_id, description=d.description, decided_by=d.decided_by))
    for action_item in data.action_items:
        db_session.add(
            ActionItem(
                summary_id=summary_id,
                description=action_item.description,
                assignee=action_item.assignee,
                due_date=action_item.due_date,
            )
        )


async def _create_summary(
    db_session: AsyncSession, filename: str, content_hash: str, data: LLMSummary
) -> SummaryRead:
    """Persist a summary and its related topics, decisions, and action items.

    Args:
        db_session (AsyncSession): Database session.
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
    try:
        db_session.add(summary)
        await db_session.flush()
        _add_children(db_session, summary.id, data)
        await db_session.commit()
    except IntegrityError:
        await db_session.rollback()
        existing = await _find_by_content_hash(db_session, content_hash)
        if existing is not None:
            return await build_summary_read(db_session, existing)
        raise

    return await build_summary_read(db_session, summary)


@router.post("/summarize")
async def summarize_audio(
    file: UploadFile,
    db_session: DbSessionDep,
    recorded_at: Annotated[date | None, Form()] = None,
    num_speakers: Annotated[int | None, Form(ge=1, le=10)] = None,
) -> SummaryRead:
    """Accepts an audio file, summarizes it, persists the result, and returns it.

    Args:
        file (UploadFile): The audio file to process (mp3, m4a, wav, flac). Max 200 MB.
        db_session (AsyncSession): Database session.
        recorded_at (date | None): Date when the meeting was recorded (ISO 8601:
            YYYY-MM-DD). Used as the reference date for relative date expressions
            in the audio (e.g., "来週月曜"). Defaults to today in Asia/Tokyo (JST).
        num_speakers (int | None): Optional number of speakers to detect. If None, the pipeline will
            determine the number of speakers automatically.

    Returns:
        SummaryRead: Persisted summary including topics, decisions, and action items.

    Raises:
        HTTPException: 413 if the file exceeds 200 MB, 415 if the actual content
            is not a recognized audio format.
    """
    if file.size is not None and file.size > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File exceeds the 200 MB limit")

    spooled, audio_digest, detected_mime = await _spool_upload(file)

    if detected_mime not in _ALLOWED_MIME_TYPES:
        spooled.close()
        raise HTTPException(status_code=415, detail="Unsupported audio format")

    content_hash = hashlib.sha256(f"{audio_digest}:{num_speakers}".encode()).hexdigest()
    existing = await _find_by_content_hash(db_session, content_hash)
    if existing is not None:
        spooled.close()
        return await build_summary_read(db_session, existing)

    segments = await _transcribe(spooled, num_speakers)

    reference_date = recorded_at or datetime.now(_MEETING_TZ).date()
    async with llm_semaphore:
        llm_result = await summarize_chain.ainvoke((segments, reference_date))

    filename = _sanitize_filename(file.filename)
    return await _create_summary(db_session, filename, content_hash, llm_result)
