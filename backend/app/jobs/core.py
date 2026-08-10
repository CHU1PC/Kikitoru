from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import func
from sqlmodel import and_, col, delete, or_, select, update

from app.db.models import JobStatus, TranscriptionJob
from app.settings.job_queue import LINEAR_WAIT_SECONDS, MAX_ATTEMPTS

if TYPE_CHECKING:
    from collections.abc import Sequence
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
            select(TranscriptionJob).where(
                col(TranscriptionJob.user_id) == user_id,
                col(TranscriptionJob.content_hash) == content_hash,
                col(TranscriptionJob.status).in_(_ACTIVE_STATUS),
            )
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


async def fetch_one(db_session: AsyncSession) -> TranscriptionJob | None:
    """取得可能なジョブを1件だけ排他的に取り出し, 新しい owner_token を発行して返す.

    候補を FOR UPDATE SKIP LOCKED で1行ロックし, 同じトランザクションで processing に遷移させる.

    Args:
        db_session (AsyncSession): DBセッション. この関数が commit する

    Returns:
        TranscriptionJob | None: 取得したジョブ (owner_token 設定済み). 対象がなければ None
    """
    candidate = (
        select(col(TranscriptionJob.id))
        .where(
            col(TranscriptionJob.status) == JobStatus.pending,
            col(TranscriptionJob.scheduled_at) <= func.now(),
        )
        .order_by(col(TranscriptionJob.scheduled_at), col(TranscriptionJob.created_at))
        .limit(1)
        .with_for_update(skip_locked=True)
        .scalar_subquery()
    )
    result = await db_session.exec(
        update(TranscriptionJob)
        .where(col(TranscriptionJob.id) == candidate)
        .values(
            status=JobStatus.processing,
            owner_token=uuid4(),
            attempts=col(TranscriptionJob.attempts) + 1,
            heartbeat_at=func.now(),
            started_at=func.coalesce(col(TranscriptionJob.started_at), func.now()),
        )
        .returning(TranscriptionJob)
    )
    job = result.scalars().first()
    await db_session.commit()
    return job


async def is_job_owner(db_session: AsyncSession, job_id: UUID, token: UUID) -> bool:
    """自分の token がまだ所有権を持つか DB から読み直して確認する.

    Args:
        db_session (AsyncSession): DBセッション
        job_id (UUID): ジョブID
        token (UUID): 確認する owner_token

    Returns:
        bool: まだ所有していれば True
    """
    owner = (
        await db_session.exec(
            select(TranscriptionJob.owner_token).where(col(TranscriptionJob.id) == job_id)
        )
    ).first()
    return owner == token


async def touch_heartbeat(db_session: AsyncSession, job_id: UUID, token: UUID) -> bool:
    """生存報告として heartbeat_at を現在時刻に更新する.

    Args:
        db_session (AsyncSession): DBセッション
        job_id (UUID): ジョブID
        token (UUID): fetch_one が発行した owner_token

    Returns:
        bool: 更新できたら True. 所有権を失っていたら False
    """
    result = await db_session.exec(
        update(TranscriptionJob)
        .where(
            col(TranscriptionJob.id) == job_id,
            col(TranscriptionJob.owner_token) == token,
        )
        .values(heartbeat_at=func.now())
    )
    await db_session.commit()
    return result.rowcount == 1


async def reclaim_orphans(db_session: AsyncSession, *, older_than_seconds: int) -> int:
    """生存報告が途絶えた processing のジョブを回収する.

    Args:
        db_session (AsyncSession): DBセッション. この関数が commit する
        older_than_seconds (int): この秒数より前が最後の生存報告なら孤児とみなす

    Returns:
        int: 回収した行数
    """
    stale = (
        col(TranscriptionJob.status) == JobStatus.processing,
        func.coalesce(col(TranscriptionJob.heartbeat_at), col(TranscriptionJob.started_at))
        < func.now() - timedelta(seconds=older_than_seconds),
    )
    exhausted = await db_session.exec(
        update(TranscriptionJob)
        .where(*stale, col(TranscriptionJob.attempts) >= MAX_ATTEMPTS)
        .values(
            status=JobStatus.failed,
            error="WorkerLost",
            owner_token=None,
            heartbeat_at=None,
            completed_at=func.now(),
        )
    )
    requeued = await db_session.exec(
        update(TranscriptionJob)
        .where(*stale, col(TranscriptionJob.attempts) < MAX_ATTEMPTS)
        .values(
            status=JobStatus.pending,
            error="WorkerLost",
            owner_token=None,
            heartbeat_at=None,
            scheduled_at=func.now(),
        )
    )
    await db_session.commit()
    return exhausted.rowcount + requeued.rowcount


async def fail_expired_jobs(db_session: AsyncSession, *, max_runtime_seconds: int) -> int:
    """初回開始から時間内に終わらなかったジョブを, 試行回数に関係なく failed で確定する.

    未着手のジョブは started_at が NULL なので比較が偽になり対象外になる.

    Args:
        db_session (AsyncSession): DBセッション. この関数が commit する
        max_runtime_seconds (int): 初回開始からこの秒数を超えたら打ち切る

    Returns:
        int: 打ち切った行数
    """
    result = await db_session.exec(
        update(TranscriptionJob)
        .where(
            col(TranscriptionJob.status).in_(_ACTIVE_STATUS),
            col(TranscriptionJob.started_at)
            < func.now() - timedelta(seconds=max_runtime_seconds),
        )
        .values(
            status=JobStatus.failed,
            error="Timeout",
            owner_token=None,
            heartbeat_at=None,
            completed_at=func.now(),
        )
    )
    await db_session.commit()
    return result.rowcount


async def release_claims(db_session: AsyncSession, tokens: Sequence[UUID]) -> int:
    """停止時に抱えているジョブを, 試行を消費せず pending に戻す.

    Args:
        db_session (AsyncSession): DBセッション. この関数が commit する
        tokens (Sequence[UUID]): 手放す owner_token の一覧

    Returns:
        int: 手放した行数
    """
    if not tokens:
        return 0
    result = await db_session.exec(
        update(TranscriptionJob)
        .where(col(TranscriptionJob.owner_token).in_(tokens))
        .values(
            status=JobStatus.pending,
            owner_token=None,
            heartbeat_at=None,
            scheduled_at=func.now(),
            attempts=col(TranscriptionJob.attempts) - 1,
        )
    )
    await db_session.commit()
    return result.rowcount


async def finish_ok(db_session: AsyncSession, job_id: UUID, token: UUID, summary_id: UUID) -> bool:
    """所有権を持っている場合にかぎり completed にし, 作成した要約を紐づける.

    Args:
        db_session (AsyncSession): DBセッション. この関数が commit する
        job_id (UUID): ジョブID
        token (UUID): fetch_one が発行した owner_token
        summary_id (UUID): 作成した要約の ID

    Returns:
        bool: 書き込めたら True. 所有権を失っていたら False
    """
    result = await db_session.exec(
        update(TranscriptionJob)
        .where(
            col(TranscriptionJob.id) == job_id,
            col(TranscriptionJob.owner_token) == token,
        )
        .values(
            status=JobStatus.completed,
            summary_id=summary_id,
            completed_at=func.now(),
            error=None,
            owner_token=None,
            heartbeat_at=None,
        )
    )
    await db_session.commit()
    return result.rowcount == 1


async def finish_retry(
    db_session: AsyncSession, job_id: UUID, token: UUID, *, error: str, attempts: int
) -> bool:
    """失敗を記録する. 試行を使い切っていれば failed で確定し, 残っていれば backoff 後に pending へ戻す.

    Args:
        db_session (AsyncSession): DBセッション. この関数が commit する
        job_id (UUID): ジョブID
        token (UUID): fetch_one が発行した owner_token
        error (str): error 列に残す内容 (例外クラス名など)
        attempts (int): このジョブの実行回数

    Returns:
        bool: 書き込めたら True. 所有権を失っていたら False
    """
    stmt = update(TranscriptionJob).where(
        col(TranscriptionJob.id) == job_id,
        col(TranscriptionJob.owner_token) == token,
    )
    if attempts >= MAX_ATTEMPTS:
        stmt = stmt.values(
            status=JobStatus.failed,
            error=error,
            owner_token=None,
            heartbeat_at=None,
            completed_at=func.now(),
        )
    else:
        stmt = stmt.values(
            status=JobStatus.pending,
            error=error,
            owner_token=None,
            heartbeat_at=None,
            scheduled_at=func.now() + timedelta(seconds=LINEAR_WAIT_SECONDS * attempts),
        )
    result = await db_session.exec(stmt)
    await db_session.commit()
    return result.rowcount == 1


async def purge_old(
    db_session: AsyncSession, *, completed_days: int, failed_days: int
) -> list[tuple[JobStatus, str]]:
    """保持期間を過ぎた終了済みジョブを削除し, 消した行の (status, media_key) を返す.

    failed の media は summaries から参照されないので, 行を消すと S3 で回収不能になる.
    completed の media は summaries が音声再生に使うので消してはいけない. 呼び出し側が振り分ける.

    Args:
        db_session (AsyncSession): DBセッション. この関数が commit する
        completed_days (int): completed を保持する日数
        failed_days (int): failed を保持する日数

    Returns:
        list[tuple[JobStatus, str]]: 削除した行の (status, media_key)
    """
    expired = (
        await db_session.exec(
            delete(TranscriptionJob)
            .where(
                or_(
                    and_(
                        col(TranscriptionJob.status) == JobStatus.completed,
                        col(TranscriptionJob.completed_at)
                        < func.now() - timedelta(days=completed_days),
                    ),
                    and_(
                        col(TranscriptionJob.status) == JobStatus.failed,
                        col(TranscriptionJob.completed_at)
                        < func.now() - timedelta(days=failed_days),
                    ),
                )
            )
            .returning(col(TranscriptionJob.status), col(TranscriptionJob.media_key))
        )
    ).all()
    await db_session.commit()
    return [(status, media_key) for status, media_key in expired]
