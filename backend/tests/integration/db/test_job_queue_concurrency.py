from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlmodel import select

from app.db.models import JobStatus, TranscriptionJob, User, UserStatus
from app.jobs.core import fetch_one

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    from uuid import UUID

    from sqlmodel.ext.asyncio.session import AsyncSession

_WORKERS = 4
_JOBS = 12
_MIN_WORKERS_WITH_WORK = 2


def _seed_pending_jobs(seed: Callable[..., None], count: int) -> list[TranscriptionJob]:
    """テスト用の user と pending ジョブを count 件保存する.

    content_hash は uq_transcription_jobs_active_hash に引っかからないよう全件別の値にする.

    Args:
        seed (Callable[..., None]): テスト DB にモデルを保存するフィクスチャ.
        count (int): 作る pending ジョブの件数.

    Returns:
        list[TranscriptionJob]: 保存した pending ジョブ (作成順).
    """
    user = User(email="queue@example.com", name="Queue", status=UserStatus.approved)
    jobs = [
        TranscriptionJob(
            user_id=user.id,
            filename=f"meeting-{index}.mp3",
            content_hash=uuid4().hex,
            media_key=f"uploads/{index}",
        )
        for index in range(count)
    ]
    seed(user, *jobs)
    return jobs


def _drain(max_claims: int) -> Callable[[AsyncSession], Awaitable[list[UUID]]]:
    """1 ワーカー分の「取れなくなるまで取得し続ける」処理を組み立てる.

    同じ行を返し続けるバグでハングしないよう回数上限を設ける.

    Args:
        max_claims (int): 取得回数の上限.

    Returns:
        Callable[[AsyncSession], Awaitable[list[UUID]]]: session を受け取り job id 列を返す関数.
    """

    async def _run(db_session: AsyncSession) -> list[UUID]:
        claimed: list[UUID] = []
        for _ in range(max_claims):
            job = await fetch_one(db_session)
            if job is None:
                return claimed
            claimed.append(job.id)
        msg = f"fetch_one did not drain within {max_claims} iterations"
        raise AssertionError(msg)

    return _run


async def _all_jobs(db_session: AsyncSession) -> list[TranscriptionJob]:
    """テスト DB の全 TranscriptionJob を返す.

    Args:
        db_session (AsyncSession): DB セッション.

    Returns:
        list[TranscriptionJob]: 全ジョブ.
    """
    return list((await db_session.exec(select(TranscriptionJob))).all())


def test_concurrent_fetch_hands_each_job_to_exactly_one_worker(
    seed: Callable[..., None], db_gather: Callable[..., list[list[UUID]]]
) -> None:
    """N ワーカーが同時に取得しても各行がちょうど 1 回だけ取得されることを確認するテスト."""
    jobs = _seed_pending_jobs(seed, _JOBS)

    per_worker = db_gather(*(_drain(_JOBS + 1) for _ in range(_WORKERS)))

    claimed = [job_id for worker_result in per_worker for job_id in worker_result]
    assert len(claimed) == _JOBS  # 件数が一致 = 取りこぼしも二重取得もない
    assert set(claimed) == {job.id for job in jobs}
    # 1 ワーカーが全部取っていたら, 実際には並行していない (逐次化している) 疑い
    assert sum(1 for worker_result in per_worker if worker_result) >= _MIN_WORKERS_WITH_WORK


def test_concurrent_fetch_stamps_every_row_with_its_own_token(
    seed: Callable[..., None],
    db_gather: Callable[..., list[list[UUID]]],
    db_call: Callable[..., list[TranscriptionJob]],
) -> None:
    """並行取得の後, 全行が processing になり token と生存時刻が入ることを確認するテスト.

    heartbeat_at と started_at が NULL のまま processing になると, 孤児判定の
    coalesce(heartbeat_at, started_at) が NULL になって比較が常に偽になり, 永久に回収されない.
    """
    _seed_pending_jobs(seed, _JOBS)

    db_gather(*(_drain(_JOBS + 1) for _ in range(_WORKERS)))

    rows = db_call(_all_jobs)
    assert {row.status for row in rows} == {JobStatus.processing}
    assert len({row.owner_token for row in rows}) == _JOBS  # token は取得ごとに別の値
    assert all(row.owner_token is not None for row in rows)
    assert all(row.heartbeat_at is not None for row in rows)
    assert all(row.started_at is not None for row in rows)
    assert all(row.attempts == 1 for row in rows)


def test_fetch_returns_none_when_queue_is_empty(db_call: Callable[..., object]) -> None:
    """キューが空なら取得は None を返すことを確認するテスト."""
    assert db_call(fetch_one) is None


def test_fetch_skips_jobs_not_yet_scheduled(
    seed: Callable[..., None], db_call: Callable[..., object]
) -> None:
    """まだ実行予定時刻に達していないジョブは取得されないことを確認するテスト."""
    user = User(email="queue@example.com", name="Queue", status=UserStatus.approved)
    waiting = TranscriptionJob(
        user_id=user.id,
        filename="waiting.mp3",
        content_hash=uuid4().hex,
        media_key="uploads/waiting",
        scheduled_at=datetime.now(UTC) + timedelta(minutes=5),
    )
    seed(user, waiting)

    assert db_call(fetch_one) is None

    rows = db_call(_all_jobs)
    assert [row.status for row in rows] == [JobStatus.pending]  # 取られずに残っている
