from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlmodel import select

from app.db.models import JobStatus, TranscriptionJob, User, UserStatus
from app.jobs.core import purge_old

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlmodel.ext.asyncio.session import AsyncSession

_COMPLETED_RETENTION_DAYS = 7
_FAILED_RETENTION_DAYS = 30
_EXPECTED_PURGED = 2


def _job(
    user_id: object,
    status: JobStatus,
    *,
    completed_at: datetime | None = None,
    created_at: datetime | None = None,
) -> TranscriptionJob:
    """指定の状態と完了時刻を持つジョブを組み立てる (保存はしない).

    Args:
        user_id (object): 所有者のユーザー ID.
        status (JobStatus): ジョブの状態.
        completed_at (datetime | None): 完了時刻. 未完了なら None.
        created_at (datetime | None): 作成時刻. 省略時は現在時刻.

    Returns:
        TranscriptionJob: 組み立てたジョブ.
    """
    return TranscriptionJob(
        user_id=user_id,  # pyright: ignore[reportArgumentType]
        status=status,
        filename="a.mp3",
        content_hash=uuid4().hex,
        media_key=f"uploads/{uuid4().hex}",
        completed_at=completed_at,
        created_at=created_at or datetime.now(UTC),
    )


async def _all_jobs(db_session: AsyncSession) -> list[TranscriptionJob]:
    """テスト DB の全 TranscriptionJob を返す.

    Args:
        db_session (AsyncSession): DB セッション.

    Returns:
        list[TranscriptionJob]: 全ジョブ.
    """
    return list((await db_session.exec(select(TranscriptionJob))).all())


def _purge(db_session: AsyncSession) -> object:
    """既定の保持期間で purge_old を呼ぶ.

    Args:
        db_session (AsyncSession): DB セッション.

    Returns:
        object: 削除した行の (status, media_key) のリスト.
    """
    return purge_old(
        db_session,
        completed_days=_COMPLETED_RETENTION_DAYS,
        failed_days=_FAILED_RETENTION_DAYS,
    )


def test_purge_removes_only_expired_finished_jobs(
    seed: Callable[..., None], db_call: Callable[..., object]
) -> None:
    """保持期間を過ぎた completed/failed だけが削除されることを確認するテスト.

    pending / processing は completed_at が NULL なので, どれだけ古くても対象外になる.
    ここが壊れると実行中のジョブが消える.
    """
    now = datetime.now(UTC)
    user = User(email="purge@example.com", name="Purge", status=UserStatus.approved)
    expired_completed = _job(user.id, JobStatus.completed, completed_at=now - timedelta(days=8))
    kept_completed = _job(user.id, JobStatus.completed, completed_at=now - timedelta(days=6))
    expired_failed = _job(user.id, JobStatus.failed, completed_at=now - timedelta(days=31))
    kept_failed = _job(user.id, JobStatus.failed, completed_at=now - timedelta(days=29))
    old_processing = _job(user.id, JobStatus.processing, created_at=now - timedelta(days=90))
    old_pending = _job(user.id, JobStatus.pending, created_at=now - timedelta(days=90))
    seed(
        user,
        expired_completed,
        kept_completed,
        expired_failed,
        kept_failed,
        old_processing,
        old_pending,
    )

    purged = db_call(_purge)

    assert len(purged) == _EXPECTED_PURGED
    remaining = {job.id for job in db_call(_all_jobs)}
    assert remaining == {kept_completed.id, kept_failed.id, old_processing.id, old_pending.id}


def test_purge_reports_media_key_of_failed_jobs(
    seed: Callable[..., None], db_call: Callable[..., object]
) -> None:
    """削除した行の media_key を返すことを確認するテスト.

    failed の音声は summaries から参照されないため, 行を消す前にキーを受け取らないと
    S3 上で回収不能になる.
    """
    now = datetime.now(UTC)
    user = User(email="purge@example.com", name="Purge", status=UserStatus.approved)
    expired_failed = _job(user.id, JobStatus.failed, completed_at=now - timedelta(days=31))
    seed(user, expired_failed)

    purged = db_call(_purge)

    assert purged == [(JobStatus.failed, expired_failed.media_key)]


def test_purge_keeps_everything_within_retention(
    seed: Callable[..., None], db_call: Callable[..., object]
) -> None:
    """保持期間内のジョブは 1 件も消えないことを確認するテスト."""
    now = datetime.now(UTC)
    user = User(email="purge@example.com", name="Purge", status=UserStatus.approved)
    fresh_completed = _job(user.id, JobStatus.completed, completed_at=now - timedelta(hours=1))
    fresh_failed = _job(user.id, JobStatus.failed, completed_at=now - timedelta(hours=1))
    seed(user, fresh_completed, fresh_failed)

    assert db_call(_purge) == []
    assert len(db_call(_all_jobs)) == _EXPECTED_PURGED
