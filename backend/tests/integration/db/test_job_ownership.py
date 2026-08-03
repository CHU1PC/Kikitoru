from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from uuid import uuid4

from app.db.models import JobStatus, TranscriptionJob, User, UserStatus
from app.db.transcription_jobs import (
    claim_job_ownership,
    clear_job_ownership,
    find_orphaned_processing_jobs,
    is_job_owner,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from uuid import UUID


def _seed_job(seed: Callable[..., None]) -> TranscriptionJob:
    """所有権テスト用の user と pending ジョブを 1 件ずつ保存する.

    Args:
        seed (Callable[..., None]): テスト DB にモデルを保存するフィクスチャ.

    Returns:
        TranscriptionJob: 保存された pending ジョブ.
    """
    user = User(email="owner@example.com", name="Owner", status=UserStatus.approved)
    job = TranscriptionJob(
        user_id=user.id,
        filename="a.mp3",
        content_hash="hash-a",
        media_key="uploads/a",
    )
    seed(user, job)
    return job


def test_first_claim_succeeds(seed: Callable[..., None], db_call: Callable[..., object]) -> None:
    """owner_attempt が NULL の状態では最初の claim が成功することを確認するテスト."""
    job = _seed_job(seed)

    assert db_call(lambda s: claim_job_ownership(s, job.id, 0)) is True
    assert db_call(lambda s: is_job_owner(s, job.id, 0)) is True


def test_same_attempt_cannot_claim_twice(seed: Callable[..., None], db_call: Callable[..., object]) -> None:
    """同じ attempt 番号での再 claim は失敗することを確認するテスト."""
    job = _seed_job(seed)
    db_call(lambda s: claim_job_ownership(s, job.id, 0))

    assert db_call(lambda s: claim_job_ownership(s, job.id, 0)) is False


def test_newer_attempt_takes_ownership(seed: Callable[..., None], db_call: Callable[..., object]) -> None:
    """より新しい attempt が所有権を奪い, 古い attempt は所有者でなくなることを確認するテスト."""
    job = _seed_job(seed)
    db_call(lambda s: claim_job_ownership(s, job.id, 0))

    assert db_call(lambda s: claim_job_ownership(s, job.id, 1)) is True
    assert db_call(lambda s: is_job_owner(s, job.id, 0)) is False
    assert db_call(lambda s: is_job_owner(s, job.id, 1)) is True


def test_older_attempt_cannot_take_back(seed: Callable[..., None], db_call: Callable[..., object]) -> None:
    """奪われた後に古い attempt が所有権を取り戻せないことを確認するテスト."""
    job = _seed_job(seed)
    db_call(lambda s: claim_job_ownership(s, job.id, 0))
    db_call(lambda s: claim_job_ownership(s, job.id, 1))

    assert db_call(lambda s: claim_job_ownership(s, job.id, 0)) is False
    assert db_call(lambda s: is_job_owner(s, job.id, 1)) is True


def test_claim_on_missing_job_returns_false(db_call: Callable[..., object]) -> None:
    """存在しないジョブ ID への claim は False を返すことを確認するテスト."""
    missing = TranscriptionJob(
        user_id=User(email="x@example.com", name="X").id,
        filename="x.mp3",
        content_hash="x",
        media_key="uploads/x",
    )

    assert db_call(lambda s: claim_job_ownership(s, missing.id, 0)) is False


def test_clear_ownership_allows_fresh_attempt_to_claim(
    seed: Callable[..., None], db_call: Callable[..., object]
) -> None:
    """所有権をリセットすると再投入したジョブが attempt 0 で claim できることを確認するテスト."""
    job = _seed_job(seed)
    db_call(lambda s: claim_job_ownership(s, job.id, 3))
    assert db_call(lambda s: claim_job_ownership(s, job.id, 0)) is False

    db_call(lambda s: clear_job_ownership(s, job.id))

    assert db_call(lambda s: claim_job_ownership(s, job.id, 0)) is True


def _job_for(user_id: UUID, *, status: JobStatus, started_at: datetime) -> TranscriptionJob:
    """指定の状態と開始時刻を持つジョブを組み立てる (保存はしない).

    Args:
        user_id (UUID): 所有者のユーザー ID.
        status (JobStatus): ジョブの状態.
        started_at (datetime): 処理開始時刻.

    Returns:
        TranscriptionJob: 組み立てたジョブ.
    """
    return TranscriptionJob(
        user_id=user_id,
        filename="a.mp3",
        content_hash=uuid4().hex,
        media_key="uploads/a",
        status=status,
        started_at=started_at,
    )


def test_find_orphaned_returns_only_stale_processing_jobs(
    seed: Callable[..., None], db_call: Callable[..., list[TranscriptionJob]]
) -> None:
    """閾値を超えた processing のジョブだけが孤児として検出されることを確認するテスト."""
    user = User(email="owner@example.com", name="Owner", status=UserStatus.approved)
    now = datetime.now(UTC)
    stale = _job_for(user.id, status=JobStatus.processing, started_at=now - timedelta(minutes=60))
    fresh = _job_for(user.id, status=JobStatus.processing, started_at=now - timedelta(minutes=10))
    completed = _job_for(user.id, status=JobStatus.completed, started_at=now - timedelta(minutes=60))
    seed(user, stale, fresh, completed)

    found = db_call(lambda s: find_orphaned_processing_jobs(s, older_than_seconds=30 * 60))

    assert [job.id for job in found] == [stale.id]
