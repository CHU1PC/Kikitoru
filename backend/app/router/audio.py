from __future__ import annotations

import hashlib
from datetime import date, datetime
from typing import TYPE_CHECKING, Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Form, HTTPException, Request, UploadFile

from app.audio.intake import ALLOWED_MIME_TYPES, MAX_UPLOAD_BYTES, sanitize_filename, spool_upload
from app.db.summaries import build_summary_read, create_summary, find_by_content_hash
from app.dependencies import (
    CurrentUser,  # noqa: TC001 — FastAPI resolves the dependency annotation at runtime
    DbSessionDep,  # noqa: TC001 — FastAPI resolves the dependency annotation at runtime
)
from app.llm.summarize import summarize_chain
from app.rate_limit import AUDIO_SUMMARIZE_RATE_LIMIT, limiter
from app.schema.summaries import (
    SummaryResponse,  # noqa: TC001 — FastAPI resolves the return annotation at runtime for response_model
)
from app.settings.config import llm_semaphore
from app.stt.pipeline import transcribe_with_diarization

if TYPE_CHECKING:
    import tempfile

    from app.stt.types import Segment


router = APIRouter(prefix="/audio", tags=["audio"])

_MEETING_TZ = ZoneInfo("Asia/Tokyo")  # default tz when the client omits recorded_at


async def _transcribe(spooled: tempfile.SpooledTemporaryFile[bytes], num_speakers: int | None = None) -> list[Segment]:
    """Spool で一時的に保存された音声ファイルを AWS Transcribe で文字起こしし、話者分離されたセグメントのリストを返す.

    Args:
        spooled (SpooledTemporaryFile): 一時的に保存された音声ファイルのバイナリストリーム
        num_speakers (int | None): 話者数. None の場合は自動で話者数を推定する. default: None

    Returns:
        list[Segment]: 話者分離されたセグメントのリスト
    """
    try:
        return await transcribe_with_diarization(spooled, num_speakers)
    finally:
        spooled.close()


@router.post("/summarize")
@limiter.limit(AUDIO_SUMMARIZE_RATE_LIMIT)  # pyright: ignore[reportUntypedFunctionDecorator, reportUnknownMemberType]
async def summarize_audio(
    request: Request,  # noqa: ARG001 — slowapi のレート制限がシグネチャから参照する
    file: UploadFile,
    db_session: DbSessionDep,
    user: CurrentUser,
    recorded_at: Annotated[date | None, Form()] = None,
    num_speakers: Annotated[int | None, Form(ge=1, le=10)] = None,
) -> SummaryResponse:
    """STT で音声を文字起こしし、LLM で要約する.

    STT で音声を文字起こしし、話者分離されたセグメントのリストを生成する。
    その後、LLM にセグメントと録音日を渡して要約を生成し、データベースに保存する。
    既に同じ音声ファイルがアップロードされている場合は、再度文字起こしや要約を行わず、既存の要約を返す。

    Args:
        request (Request): FastAPI の Request オブジェクト。レート制限のために使用される。
        file (UploadFile): 音声ファイルのアップロード。最大 200 MB
        db_session (AsyncSession): SQLAlchemy の非同期セッション.
        user (User): 現在のユーザー。FastAPI の依存性注入で解決される.
        recorded_at (date | None): 録音日。クライアントが指定しない場合は現在日付を使用する. default: None
        num_speakers (int | None): 話者数. None の場合は自動で話者数を推定する. default: None

    Returns:
        SummaryResponse: トピック, 要約, 話者分離されたセグメントのリストを含む要約オブジェクト.

    Raises:
        HTTPException: 413 - アップロードされたファイルが 200 MB を超える場合
        HTTPException: 415 - アップロードされたファイルの MIME タイプが ALLOWED_MIME_TYPES に含まれない場合
        HTTPException: 422 - 音声ファイルからセグメントが生成されなかった場合
    """
    if file.size is not None and file.size > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File exceeds the 200 MB limit")

    spooled, audio_digest, detected_mime = await spool_upload(file)

    if detected_mime not in ALLOWED_MIME_TYPES:
        spooled.close()
        raise HTTPException(status_code=415, detail="Unsupported audio format")

    content_hash = hashlib.sha256(f"{audio_digest}:{num_speakers}".encode()).hexdigest()
    existing = await find_by_content_hash(db_session, user.id, content_hash)
    if existing is not None:
        spooled.close()
        return await build_summary_read(db_session, existing)

    segments = await _transcribe(spooled, num_speakers)
    if not segments:
        raise HTTPException(status_code=422, detail="No segments were generated from the audio file")

    reference_date = recorded_at or datetime.now(_MEETING_TZ).date()
    async with llm_semaphore:
        llm_result = await summarize_chain.ainvoke((segments, reference_date))

    filename = sanitize_filename(file.filename)
    return await create_summary(db_session, user.id, filename, content_hash, llm_result)
