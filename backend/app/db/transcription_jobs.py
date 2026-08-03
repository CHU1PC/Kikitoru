from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlmodel import col, or_, select, update

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


async def add_pending_job(
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
    """Pending の TranscriptionJob をセッションに追加する (commit はしない).

    Args:
        db_session (AsyncSession): DB セッション. commit は呼び出し側でおこなう.
        job_id (UUID): ジョブID.
        user_id (UUID): ユーザー ID.
        filename (str): アップロードされた音声ファイル名
        content_hash (str): 音声と話者数の SHA-256 hex.
        media_key (str): 音声/動画の S3 キー.
        num_speakers (int | None): 話者数のヒント (1-10).
        recorded_at (date | None): 会議が録音された日付.

    Returns:
        TranscriptionJob: セッションに追加された TranscriptionJob
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
    await db_session.flush()
    return job


async def claim_job_ownership(db_session: AsyncSession, job_id: UUID, attempt: int) -> bool:
    """楽観的に実行所有権を取得する. より新しい attempt が常に勝つ.

    Args:
        db_session (AsyncSession): DBセッション
        job_id (UUID): ジョブID
        attempt (int): procrastinate の attempt 番号 (context.job.attempts)

    Returns:
        bool: 所有権を取得できたら True. 他の attempt に取られていたら False
    """
    result = await db_session.exec(
        update(TranscriptionJob)
        .where(
            col(TranscriptionJob.id) == job_id,
            or_(
                col(TranscriptionJob.owner_attempt).is_(None),
                col(TranscriptionJob.owner_attempt) < attempt,
            ),
        )
        .values(owner_attempt=attempt)
    )
    await db_session.commit()
    return result.rowcount == 1


async def is_job_owner(db_session: AsyncSession, job_id: UUID, attempt: int) -> bool:
    """自分の attempt がまだ所有権を持つか DB から読み直して確認する.

    ORM オブジェクト経由だと identity map の古い値が返るため, 列を直接 select する.

    Args:
        db_session (AsyncSession): DBセッション
        job_id (UUID): ジョブID
        attempt (int): 確認する attempt 番号

    Returns:
        bool: まだ所有していれば True
    """
    owner = (
        await db_session.exec(
            select(TranscriptionJob.owner_attempt).where(col(TranscriptionJob.id) == job_id)
        )
    ).first()
    return owner == attempt


async def clear_job_ownership(db_session: AsyncSession, job_id: UUID) -> None:
    """所有権をリセットする. 再投入したジョブが attempt 0 で claim できるようにする.

    Args:
        db_session (AsyncSession): DBセッション
        job_id (UUID): ジョブID
    """
    await db_session.exec(
        update(TranscriptionJob)
        .where(col(TranscriptionJob.id) == job_id)
        .values(owner_attempt=None)
    )
    await db_session.commit()


async def find_orphaned_processing_jobs(
    db_session: AsyncSession, *, older_than_seconds: int
) -> list[TranscriptionJob]:
    """閾値を超えて processing のままのジョブを返す.

    キュー側の行が消えて誰にも回収されなくなったジョブを, 自前のテーブルから検出する.
    閾値は正常な最大実行時間 (STT + LLM + 余裕) を上回っている必要がある.

    Args:
        db_session (AsyncSession): DBセッション
        older_than_seconds (int): この秒数より前に開始したジョブを対象にする

    Returns:
        list[TranscriptionJob]: 孤児化した可能性のあるジョブ
    """
    threshold = datetime.now(UTC) - timedelta(seconds=older_than_seconds)
    return list(
        (
            await db_session.exec(
                select(TranscriptionJob).where(
                    col(TranscriptionJob.status) == JobStatus.processing,
                    col(TranscriptionJob.started_at) < threshold,
                )
            )
        ).all()
    )


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


async def mark_failed(db_session: AsyncSession, job: TranscriptionJob, error: str, *, is_final: bool) -> None:
    """失敗を記録する. is_final=True の時のみ status=failed に確定する.

    Args:
        db_session (AsyncSession): DBセッション
        job (TranscriptionJob): 失敗したジョブ.
        error (str): エラー内容
        is_final (bool): True なら status=failed 確定. False なら error だけ更新 (retry 中は processing のまま)
    """
    job.error = error
    if is_final:
        job.status = JobStatus.failed
        job.completed_at = datetime.now(UTC)
    db_session.add(job)
    await db_session.commit()


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
