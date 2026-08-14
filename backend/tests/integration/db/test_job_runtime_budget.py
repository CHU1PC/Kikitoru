from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlmodel import select

from app.db.models import JobStatus, TranscriptionJob, User, UserStatus
from app.jobs.core import fail_expired_jobs

if TYPE_CHECKING:
    from collections.abc import Callable
    from uuid import UUID

    from sqlmodel.ext.asyncio.session import AsyncSession

_MAX_RUNTIME_SECONDS = 45 * 60


def _job(
    user_id: UUID,
    status: JobStatus,
    *,
    started_at: datetime | None,
    owner_token: UUID | None = None,
) -> TranscriptionJob:
    """指定の状態と開始時刻を持つジョブを組み立てる (保存はしない).

    Args:
        user_id (UUID): 所有者のユーザー ID.
        status (JobStatus): ジョブの状態.
        started_at (datetime | None): 初回開始時刻. 未着手なら None.
        owner_token (UUID | None): 実行中なら所有者の token.

    Returns:
        TranscriptionJob: 組み立てたジョブ.
    """
    return TranscriptionJob(
        user_id=user_id,
        status=status,
        filename="a.mp3",
        content_hash=uuid4().hex,
        media_key="uploads/a",
        started_at=started_at,
        owner_token=owner_token,
        heartbeat_at=started_at if owner_token else None,
    )


async def _all_jobs(db_session: AsyncSession) -> list[TranscriptionJob]:
    """テスト DB の全 TranscriptionJob を返す.

    Args:
        db_session (AsyncSession): DB セッション.

    Returns:
        list[TranscriptionJob]: 全ジョブ.
    """
    return list((await db_session.exec(select(TranscriptionJob))).all())


def _expire(db_session: AsyncSession) -> object:
    """既定の上限で fail_expired_jobs を呼ぶ.

    Args:
        db_session (AsyncSession): DB セッション.

    Returns:
        object: 打ち切った行数.
    """
    return fail_expired_jobs(db_session, max_runtime_seconds=_MAX_RUNTIME_SECONDS)


def test_expired_processing_job_is_failed(
    seed: Callable[..., None], db_call: Callable[..., object]
) -> None:
    """上限を超えて実行中のジョブが failed で確定することを確認するテスト."""
    user = User(email="budget@example.com", name="Budget", status=UserStatus.approved)
    owner = uuid4()
    job = _job(
        user.id,
        JobStatus.processing,
        started_at=datetime.now(UTC) - timedelta(minutes=50),
        owner_token=owner,
    )
    seed(user, job)

    assert db_call(_expire) == 1

    dead = db_call(_all_jobs)[0]
    assert dead.status is JobStatus.failed
    assert dead.error == "Timeout"
    assert dead.owner_token is None  # 実行中の worker の書き込みは以後弾かれる
    assert dead.completed_at is not None


def test_expired_pending_job_is_failed(
    seed: Callable[..., None], db_call: Callable[..., object]
) -> None:
    """待機中の pending も上限を超えていれば failed になることを確認するテスト.

    ここを対象外にすると, 待機中のジョブが上限をすり抜ける.
    """
    user = User(email="budget@example.com", name="Budget", status=UserStatus.approved)
    job = _job(user.id, JobStatus.pending, started_at=datetime.now(UTC) - timedelta(minutes=50))
    seed(user, job)

    assert db_call(_expire) == 1
    assert db_call(_all_jobs)[0].status is JobStatus.failed


def test_job_within_budget_is_untouched(
    seed: Callable[..., None], db_call: Callable[..., object]
) -> None:
    """上限内のジョブには触れないことを確認するテスト."""
    user = User(email="budget@example.com", name="Budget", status=UserStatus.approved)
    owner = uuid4()
    job = _job(
        user.id,
        JobStatus.processing,
        started_at=datetime.now(UTC) - timedelta(minutes=44),
        owner_token=owner,
    )
    seed(user, job)

    assert db_call(_expire) == 0

    alive = db_call(_all_jobs)[0]
    assert alive.status is JobStatus.processing
    assert alive.owner_token == owner


def test_unstarted_job_is_never_expired(
    seed: Callable[..., None], db_call: Callable[..., object]
) -> None:
    """未着手 (started_at が NULL) のジョブは対象外であることを確認するテスト.

    投入から時間が経っていても, 実行が始まっていなければ予算を消費していない.
    """
    user = User(email="budget@example.com", name="Budget", status=UserStatus.approved)
    job = _job(user.id, JobStatus.pending, started_at=None)
    job.created_at = datetime.now(UTC) - timedelta(days=3)
    seed(user, job)

    assert db_call(_expire) == 0
    assert db_call(_all_jobs)[0].status is JobStatus.pending


def test_finished_jobs_are_untouched(
    seed: Callable[..., None], db_call: Callable[..., object]
) -> None:
    """終了済みのジョブは上書きされないことを確認するテスト."""
    user = User(email="budget@example.com", name="Budget", status=UserStatus.approved)
    old = datetime.now(UTC) - timedelta(days=1)
    done = _job(user.id, JobStatus.completed, started_at=old)
    dead = _job(user.id, JobStatus.failed, started_at=old)
    seed(user, done, dead)

    assert db_call(_expire) == 0

    statuses = sorted(job.status for job in db_call(_all_jobs))
    assert statuses == sorted([JobStatus.completed, JobStatus.failed])
