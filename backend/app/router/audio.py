from __future__ import annotations

import hashlib
from datetime import (
    date,  # ruff:ignore[typing-only-standard-library-import] - FastAPI resolves the dependency annotation at runtime
)
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Form, HTTPException, Request, UploadFile
from procrastinate.exceptions import AlreadyEnqueued
from sqlalchemy.exc import IntegrityError

from app.audio.intake import ALLOWED_MIME_TYPES, MAX_UPLOAD_BYTES, sanitize_filename, spool_upload
from app.db.models import JobStatus
from app.db.summaries import find_by_content_hash
from app.db.transcription_jobs import add_pending_job, find_active_job_by_hash, get_owned_job, list_active_jobs
from app.dependencies import (
    ApprovedUser,  # ruff:ignore[typing-only-first-party-import] — FastAPI resolves the dependency annotation at runtime
    DbSessionDep,  # ruff:ignore[typing-only-first-party-import] — FastAPI resolves the dependency annotation at runtime
)
from app.queue.tasks import process_transcription_job
from app.rate_limit import AUDIO_SUMMARIZE_RATE_LIMIT, limiter
from app.schema.summaries import TranscriptionJobResponse
from app.storage import delete_object, persist_upload

router = APIRouter(prefix="/audio", tags=["audio"])


@router.post("/summarize", status_code=202)
@limiter.limit(AUDIO_SUMMARIZE_RATE_LIMIT)  # pyright: ignore[reportUntypedFunctionDecorator, reportUntypedClassDecorator, reportUnknownMemberType]
async def summarize_audio_endpoint(
    request: Request,  # ruff:ignore[unused-function-argument] — FastAPI resolves the dependency annotation at runtime
    file: UploadFile,
    db_session: DbSessionDep,
    user: ApprovedUser,
    recorded_at: Annotated[date | None, Form()] = None,
    num_speakers: Annotated[int | None, Form(ge=1, le=10)] = None,
) -> TranscriptionJobResponse:
    """音声/動画をアップロードし, 非同期の文字起こし・要約ジョブを登録する.

    Args:
        request (Request): FastAPI の Request オブジェクト
        file (UploadFile): アップロードされた音声/動画ファイル
        db_session (DbSessionDep): データベースセッション
        user (ApprovedUser): 承認されたユーザー
        recorded_at (Annotated[date  |  None, Form, optional): 記録日時
        num_speakers (Annotated[int  |  None, Form, optional): 発話者の数

    Returns:
        TranscriptionJobResponse: 非同期文字起こしジョブの状態レスポンス

    Raises:
        HTTPException: 409 - 同一内容の要約が既にゴミ箱にある場合
        HTTPException: 413 - アップロードファイルが最大サイズを超えた場合
        HTTPException: 415 - サポートされていないファイルタイプの場合
        HTTPException: 500 - Job 登録に失敗 (並行 race で敗北したが winner も見当たらない想定外)
        RuntimeError: SQLAlchemy raw connection が None (想定外の内部状態)
    """
    if file.size is not None and file.size > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"File exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit")

    spooled, audio_digest, detected_mime = await spool_upload(file)
    try:
        if detected_mime not in ALLOWED_MIME_TYPES:
            raise HTTPException(status_code=415, detail=f"Unsupported file type: {detected_mime}")

        content_hash = hashlib.sha256(f"{audio_digest}:{num_speakers}".encode()).hexdigest()

        # 1. 既存の要約があるか確認
        existing = await find_by_content_hash(db_session, user.id, content_hash)
        if existing is not None:
            if existing.deleted_at is not None:
                # 同一内容の要約がゴミ箱にある -> 新規作成せず, その旨を伝える (復元機能は将来対応)
                raise HTTPException(status_code=409, detail="この音声の要約は既にゴミ箱にあります")
            return TranscriptionJobResponse(
                id=uuid4(),
                status=JobStatus.completed,
                filename=existing.filename,
                created_at=existing.created_at,
                summary_id=existing.id,
            )

        # 2. 進行中のジョブあり
        active = await find_active_job_by_hash(db_session, user.id, content_hash)
        if active is not None:
            return TranscriptionJobResponse.model_validate(active)

        # 3. 新規
        job_id = uuid4()
        media_key = await persist_upload(spooled, job_id)
        try:  # ruff: ignore[too-many-statements-in-try-clause] - INSERT + defer を atomic にするため
            job = await add_pending_job(  # flush() を行うため IntegrityError が起こりうる
                db_session,
                job_id=job_id,
                user_id=user.id,
                filename=sanitize_filename(file.filename),
                content_hash=content_hash,
                media_key=media_key,
                num_speakers=num_speakers,
                recorded_at=recorded_at,
            )
            psycopg_conn = (await (await db_session.connection()).get_raw_connection()).driver_connection
            if psycopg_conn is None:
                msg = "SQLAlchemy raw connection has no driver_connection"
                raise RuntimeError(msg)

            await process_transcription_job.configure(
                connection=psycopg_conn,
                queueing_lock=f"stt:{user.id}:{content_hash}",
                lock=f"stt:{job_id}",
            ).defer_async(job_id=str(job.id), user_id=str(user.id))

            await db_session.commit()
            return TranscriptionJobResponse.model_validate(job)
        except (IntegrityError, AlreadyEnqueued) as e:
            await db_session.rollback()
            existing = await find_active_job_by_hash(db_session, user.id, content_hash)
            if existing is not None:
                await delete_object(media_key)  # 勝者が別 id → 今 upload した media は孤児
                return TranscriptionJobResponse.model_validate(existing)
            raise HTTPException(status_code=500, detail="Failed to enqueue transcription job") from e
    finally:
        spooled.close()


@router.get("/jobs/{job_id}")
async def get_job_endpoint(
    job_id: UUID, db_session: DbSessionDep, user: ApprovedUser
) -> TranscriptionJobResponse:
    """1件のジョブ状態を返す (polling 用). 他ユーザー/存在しないは 404.

    Args:
        job_id (UUID): ジョブID
        db_session (AsyncSession): データベースセッション
        user (ApprovedUser): 承認されたユーザー

    Returns:
        TranscriptionJobResponse: ジョブの状態

    Raises:
        HTTPException: 404 - ジョブが見つからない場合
    """
    job = await get_owned_job(db_session, user.id, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return TranscriptionJobResponse.model_validate(job)


@router.get("/jobs")
async def list_jobs_endpoint(
    db_session: DbSessionDep, user: ApprovedUser
) -> list[TranscriptionJobResponse]:
    """自分の進行中(pending/processing)ジョブ一覧を返す (サイドバーの pending 項目用).

    Args:
        db_session (AsyncSession): データベースセッション
        user (ApprovedUser): 承認されたユーザー

    Returns:
        list[TranscriptionJobResponse]: 進行中ジョブの状態リスト
    """
    jobs = await list_active_jobs(db_session, user.id)
    return [TranscriptionJobResponse.model_validate(j) for j in jobs]
