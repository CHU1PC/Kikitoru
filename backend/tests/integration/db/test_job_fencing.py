from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlmodel import col, select

from app.db.models import JobStatus, TranscriptionJob, User, UserStatus
from app.jobs.core import (
    MAX_ATTEMPTS,
    fetch_one,
    finish_ok,
    finish_retry,
    reclaim_orphans,
    release_claims,
    touch_heartbeat,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from uuid import UUID

    from sqlmodel.ext.asyncio.session import AsyncSession

_ORPHAN_THRESHOLD_SECONDS = 10 * 60
_ATTEMPTS_BEFORE_RELEASE = 2


def _seed_processing_job(
    seed: Callable[..., None],
    *,
    token: UUID,
    heartbeat_at: datetime,
    attempts: int = 1,
) -> TranscriptionJob:
    """指定の所有者・生存報告時刻を持つ processing ジョブを保存する.

    Args:
        seed (Callable[..., None]): テスト DB にモデルを保存するフィクスチャ.
        token (UUID): 所有者の owner_token.
        heartbeat_at (datetime): 最後の生存報告時刻.
        attempts (int): これまでの実行回数.

    Returns:
        TranscriptionJob: 保存された processing ジョブ.
    """
    user = User(email="fence@example.com", name="Fence", status=UserStatus.approved)
    job = TranscriptionJob(
        user_id=user.id,
        status=JobStatus.processing,
        filename="a.mp3",
        content_hash=uuid4().hex,
        media_key="uploads/a",
        owner_token=token,
        attempts=attempts,
        started_at=heartbeat_at,
        heartbeat_at=heartbeat_at,
    )
    seed(user, job)
    return job


def _fetch(job_id: UUID) -> Callable[[AsyncSession], object]:
    """job_id の行を DB から読み直す関数を返す.

    Args:
        job_id (UUID): 読むジョブの ID.

    Returns:
        Callable[[AsyncSession], object]: session を受け取りジョブを返す関数.
    """

    async def _run(db_session: AsyncSession) -> TranscriptionJob | None:
        return (
            await db_session.exec(
                select(TranscriptionJob).where(col(TranscriptionJob.id) == job_id)
            )
        ).first()

    return _run


def test_stale_owner_cannot_touch_heartbeat(
    seed: Callable[..., None], db_call: Callable[..., object]
) -> None:
    """所有権を失った worker の生存報告が無視されることを確認するテスト.

    ここが通ると死んだと判定された worker が自分で孤児判定を打ち消し続け,
    ジョブが永久に回収されなくなる.
    """
    winner, loser = uuid4(), uuid4()
    stale_beat = datetime.now(UTC) - timedelta(minutes=20)
    job = _seed_processing_job(seed, token=winner, heartbeat_at=stale_beat)

    assert db_call(lambda s: touch_heartbeat(s, job.id, loser)) is False
    assert db_call(_fetch(job.id)).heartbeat_at == stale_beat

    assert db_call(lambda s: touch_heartbeat(s, job.id, winner)) is True


def test_stale_owner_cannot_write_result(
    seed: Callable[..., None], db_call: Callable[..., object]
) -> None:
    """回収された後, 旧所有者が結果を書き戻せないことを確認するテスト (fencing の本丸)."""
    old_owner = uuid4()
    job = _seed_processing_job(
        seed, token=old_owner, heartbeat_at=datetime.now(UTC) - timedelta(minutes=20)
    )

    assert db_call(lambda s: reclaim_orphans(s, older_than_seconds=_ORPHAN_THRESHOLD_SECONDS)) == 1

    requeued = db_call(_fetch(job.id))
    assert requeued.status is JobStatus.pending
    assert requeued.owner_token is None  # 次の fetch_one が新しい token を発行できる

    assert db_call(lambda s: finish_ok(s, job.id, old_owner, uuid4())) is False
    assert db_call(_fetch(job.id)).status is JobStatus.pending


def test_reclaim_leaves_live_jobs_alone(
    seed: Callable[..., None], db_call: Callable[..., object]
) -> None:
    """生存報告が新しいジョブは長時間走っていても回収されないことを確認するテスト."""
    owner = uuid4()
    job = _seed_processing_job(
        seed, token=owner, heartbeat_at=datetime.now(UTC) - timedelta(seconds=30)
    )

    assert db_call(lambda s: reclaim_orphans(s, older_than_seconds=_ORPHAN_THRESHOLD_SECONDS)) == 0
    assert db_call(_fetch(job.id)).owner_token == owner


def test_reclaim_fails_job_that_exhausted_its_attempts(
    seed: Callable[..., None], db_call: Callable[..., object]
) -> None:
    """試行を使い切った孤児は pending でなく failed に落ちることを確認するテスト.

    ここを pending に戻すと実行のたびに worker を落とすジョブが永久ループする.
    """
    job = _seed_processing_job(
        seed,
        token=uuid4(),
        heartbeat_at=datetime.now(UTC) - timedelta(minutes=20),
        attempts=MAX_ATTEMPTS,
    )

    assert db_call(lambda s: reclaim_orphans(s, older_than_seconds=_ORPHAN_THRESHOLD_SECONDS)) == 1

    dead = db_call(_fetch(job.id))
    assert dead.status is JobStatus.failed
    assert dead.completed_at is not None
    assert dead.error == "WorkerLost"


def test_retry_returns_job_to_pending_with_backoff(
    seed: Callable[..., None], db_call: Callable[..., object]
) -> None:
    """上限未満の失敗は pending に戻り scheduled_at が未来になることを確認するテスト."""
    owner = uuid4()
    job = _seed_processing_job(seed, token=owner, heartbeat_at=datetime.now(UTC), attempts=1)

    assert db_call(lambda s: finish_retry(s, job.id, owner, error="TimeoutError", attempts=1)) is True

    fresh = db_call(_fetch(job.id))
    assert fresh.status is JobStatus.pending
    assert fresh.owner_token is None
    assert fresh.error == "TimeoutError"
    assert fresh.scheduled_at > datetime.now(UTC)
    assert fresh.completed_at is None


def test_retry_gives_up_at_max_attempts(
    seed: Callable[..., None], db_call: Callable[..., object]
) -> None:
    """試行を使い切った失敗は failed で確定することを確認するテスト."""
    owner = uuid4()
    job = _seed_processing_job(
        seed, token=owner, heartbeat_at=datetime.now(UTC), attempts=MAX_ATTEMPTS
    )

    db_call(lambda s: finish_retry(s, job.id, owner, error="TimeoutError", attempts=MAX_ATTEMPTS))

    dead = db_call(_fetch(job.id))
    assert dead.status is JobStatus.failed
    assert dead.completed_at is not None


def test_release_claims_returns_the_job_immediately(
    seed: Callable[..., None], db_call: Callable[..., object]
) -> None:
    """停止時の手放しが backoff なしで pending に戻すことを確認するテスト."""
    owner = uuid4()
    job = _seed_processing_job(
        seed, token=owner, heartbeat_at=datetime.now(UTC), attempts=_ATTEMPTS_BEFORE_RELEASE
    )

    assert db_call(lambda s: release_claims(s, [owner])) == 1

    released = db_call(_fetch(job.id))
    assert released.status is JobStatus.pending
    assert released.owner_token is None
    assert released.scheduled_at <= datetime.now(UTC)


def test_release_then_refetch_does_not_consume_an_attempt(
    seed: Callable[..., None], db_call: Callable[..., object]
) -> None:
    """停止 -> 再取得を通しても試行が減らないことを確認するテスト.

    fetch_one が取得時に加算するので, release_claims が戻さないと
    デプロイのたびにリトライ枠を 1 消費してしまう.
    """
    user = User(email="release@example.com", name="Release", status=UserStatus.approved)
    seed(
        user,
        TranscriptionJob(
            user_id=user.id,
            filename="a.mp3",
            content_hash=uuid4().hex,
            media_key="uploads/a",
        ),
    )

    first = db_call(fetch_one)
    assert first.attempts == 1

    db_call(lambda s: release_claims(s, [first.owner_token]))
    second = db_call(fetch_one)

    assert second.attempts == 1  # 停止をはさんでも実行回数は 1 回のまま
