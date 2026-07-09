from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlmodel import col, select

from app.db.models import JobStatus, TranscriptionJob

if TYPE_CHECKING:
    from datetime import date
    from uuid import UUID

    from sqlmodel.ext.asyncio.session import AsyncSession

_ACTIVE_STATUS = (JobStatus.pending, JobStatus.processing)


async def find_active_job_by_hash(
    db_session: AsyncSession, user_id: UUID, content_hash: str
) -> TranscriptionJob | None:
    """このユーザーの同一音声に対する進行中(pending/processing)のジョブを返す. なければ None.

    Args:
        db_session (AsyncSession): DBセッション
        user_id (UUID): ユーザーID
        content_hash (str): 音声と話者数のSHA-256 hex

    Returns:
        TranscriptionJob | None: 進行中のジョブ. なければ None
    """
    return (
        await db_session.exec(
            select(TranscriptionJob)
            .where(
                col(TranscriptionJob.user_id) == user_id,
                col(TranscriptionJob.content_hash) == content_hash,
                col(TranscriptionJob.status).in_(_ACTIVE_STATUS),
            )
            .order_by(col(TranscriptionJob.created_at).desc())
        )
    ).first()


async def create_job(
    db_session: AsyncSession,
    *,
    job_id: UUID,
    user_id: UUID,
    filename: str,
    content_hash: str,
    media_key: str,
    num_speakers: int | None,
    recorded_at: date | None,
) -> TranscriptionJob:
    """文字起こしジョブを作成する.

    Args:
        db_session (AsyncSession): DBセッション
        job_id (UUID): ジョブID
        user_id (UUID): ユーザーID
        filename (str): アップロードされた音声ファイル名
        content_hash (str): 音声と話者数のSHA-256 hex
        media_key (str): 音声/動画の S3 キー
        num_speakers (int | None): 話者数のヒント(1-10). Noneなら自動推定
        recorded_at (date | None): 会議が録音された日付. Noneなら不明

    Returns:
        TranscriptionJob: 作成された文字起こしジョブ
    """
    job = TranscriptionJob(
        id=job_id,
        user_id=user_id,
        status=JobStatus.pending,
        filename=filename,
        content_hash=content_hash,
        num_speakers=num_speakers,
        media_key=media_key,
        recorded_at=recorded_at,
    )
    db_session.add(job)
    await db_session.commit()
    return job


async def claim_next_job(db_session: AsyncSession) -> TranscriptionJob | None:
    """Pending のジョブを取得して status を processing に更新する.

    FOR UPDATE SKIP LOCKED で他 worker がロック中の行を飛ばし、最古の pending を1件ロック取得して
    processing に更新する。複数 worker でも二重処理しない。

    Args:
        db_session (AsyncSession): DBセッション

    Returns:
        TranscriptionJob | None: 取得したジョブ. なければ None
    """
    stmt = (
        select(TranscriptionJob)
        .where(col(TranscriptionJob.status) == JobStatus.pending)
        .order_by(col(TranscriptionJob.created_at).asc())
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    job = (await db_session.exec(stmt)).first()
    if job is None:
        return None
    job.status = JobStatus.processing
    job.started_at = datetime.now(UTC)
    db_session.add(job)
    await db_session.commit()
    return job


async def mark_completed(db_session: AsyncSession, job: TranscriptionJob, summary_id: UUID) -> None:
    """ジョブを completed にし, 作成した要約を紐づける.

    Args:
        db_session (AsyncSession): DBセッション
        job (TranscriptionJob): 完了したジョブ.
        summary_id (UUID): 作成した要約の ID
    """
    job.status = JobStatus.completed
    job.summary_id = summary_id
    job.completed_at = datetime.now(UTC)
    job.error = None
    db_session.add(job)
    await db_session.commit()


async def mark_failed(db_session: AsyncSession, job: TranscriptionJob, error: str, *, max_attempts: int = 3) -> None:
    """失敗を記録する. attempts が上限未満なら pending に戻して再試行する.

    Args:
        db_session (AsyncSession): DBセッション
        job (TranscriptionJob): 失敗したジョブ.
        error (str): エラー内容
        max_attempts (int, optional): 最大試行回数. Defaults to 3.
    """
    job.attempts += 1
    job.error = error
    if job.attempts < max_attempts:
        job.status = JobStatus.pending
        job.started_at = None
    else:
        job.status = JobStatus.failed
        job.completed_at = datetime.now(UTC)
    db_session.add(job)
    await db_session.commit()


async def reclaim_stale_jobs(db_session: AsyncSession, *, older_than_seconds: int = 60 * 60) -> int:
    """長時間 processing のままのジョブを pending に戻す.

    Args:
        db_session (AsyncSession): DBセッション
        older_than_seconds (int, optional): この秒数より古いジョブを stale とみなす. Defaults to 60*60.

    Returns:
        int: 復帰させたジョブの件数
    """
    threshold = datetime.now(UTC) - timedelta(seconds=older_than_seconds)
    stmt = select(TranscriptionJob).where(
        col(TranscriptionJob.status) == JobStatus.processing,
        col(TranscriptionJob.started_at) < threshold,
    )
    stale = (await db_session.exec(stmt)).all()
    for job in stale:
        job.status = JobStatus.pending
        job.started_at = None
        db_session.add(job)
    if stale:
        await db_session.commit()
    return len(stale)


async def get_owned_job(
    db_session: AsyncSession, user_id: UUID, job_id: UUID
) -> TranscriptionJob | None:
    """Owner スコープで job を1件取得する. 他ユーザー/存在しない場合は None.

    Args:
        db_session (AsyncSession): DBセッション
        user_id (UUID): 所有者のユーザーID
        job_id (UUID): ジョブID

    Returns:
        TranscriptionJob | None: 一致するジョブ. なければ None
    """
    return (
        await db_session.exec(
            select(TranscriptionJob).where(
                col(TranscriptionJob.id) == job_id,
                col(TranscriptionJob.user_id) == user_id,
            )
        )
    ).first()


async def list_active_jobs(db_session: AsyncSession, user_id: UUID) -> list[TranscriptionJob]:
    """User の進行中(pending/processing)ジョブを新しい順に返す (サイドバーの pending 表示用).

    Args:
        db_session (AsyncSession): DBセッション
        user_id (UUID): 所有者のユーザーID

    Returns:
        list[TranscriptionJob]: 進行中ジョブのリスト (新しい順)
    """
    return list(
        (
            await db_session.exec(
                select(TranscriptionJob)
                .where(
                    col(TranscriptionJob.user_id) == user_id,
                    col(TranscriptionJob.status).in_(_ACTIVE_STATUS),
                )
                .order_by(col(TranscriptionJob.created_at).desc())
            )
        ).all()
    )
