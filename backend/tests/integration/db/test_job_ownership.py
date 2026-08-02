from __future__ import annotations

from typing import TYPE_CHECKING

from app.db.models import TranscriptionJob, User, UserStatus
from app.db.transcription_jobs import claim_job_ownership, is_job_owner

if TYPE_CHECKING:
    from collections.abc import Callable


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
