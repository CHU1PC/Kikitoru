from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlmodel import select

from app.db.models import (
    ActionItem,
    Decision,
    JobStatus,
    Summary,
    Topic,
    TranscriptionJob,
    TranscriptSegment,
    User,
    UserStatus,
)
from app.summaries.core import purge_expired_summaries

if TYPE_CHECKING:
    from collections.abc import Callable
    from uuid import UUID

    from sqlmodel.ext.asyncio.session import AsyncSession

_TRASH_RETENTION_DAYS = 30
_EXPECTED_PURGED = 1
_EXPECTED_KEPT = 2


def _summary(
    user_id: object,
    *,
    deleted_at: datetime | None = None,
    media_key: str | None = None,
) -> Summary:
    """指定の削除時刻を持つ要約を組み立てる (保存はしない).

    Args:
        user_id (object): 所有者のユーザー ID.
        deleted_at (datetime | None): ゴミ箱に入れた時刻. アクティブなら None.
        media_key (str | None): 元音声の S3 キー.

    Returns:
        Summary: 組み立てた要約.
    """
    return Summary(
        user_id=user_id,  # pyright: ignore[reportArgumentType]
        filename="a.mp3",
        content_hash=uuid4().hex,
        overall_summary="全体の要約",
        media_key=media_key,
        deleted_at=deleted_at,
    )


async def _all_summaries(db_session: AsyncSession) -> list[Summary]:
    """テスト DB の全 Summary を返す.

    Args:
        db_session (AsyncSession): DB セッション.

    Returns:
        list[Summary]: 全要約.
    """
    return list((await db_session.exec(select(Summary))).all())


async def _all_jobs(db_session: AsyncSession) -> list[TranscriptionJob]:
    """テスト DB の全 TranscriptionJob を返す.

    Args:
        db_session (AsyncSession): DB セッション.

    Returns:
        list[TranscriptionJob]: 全ジョブ.
    """
    return list((await db_session.exec(select(TranscriptionJob))).all())


async def _child_summary_ids(db_session: AsyncSession) -> set[UUID]:
    """子テーブルに残っている行の summary_id を集めて返す.

    Args:
        db_session (AsyncSession): DB セッション.

    Returns:
        set[UUID]: topic/decision/action item/segment が参照している summary_id.
    """
    topics = (await db_session.exec(select(Topic))).all()
    decisions = (await db_session.exec(select(Decision))).all()
    action_items = (await db_session.exec(select(ActionItem))).all()
    segments = (await db_session.exec(select(TranscriptSegment))).all()
    return {row.summary_id for row in (*topics, *decisions, *action_items, *segments)}


def _purge(db_session: AsyncSession) -> object:
    """既定の保持期間で purge_expired_summaries を呼ぶ.

    Args:
        db_session (AsyncSession): DB セッション.

    Returns:
        object: 削除した行数.
    """
    return purge_expired_summaries(db_session, retention_days=_TRASH_RETENTION_DAYS)


def test_purge_removes_only_expired_trashed_summaries(
    seed: Callable[..., None], db_call: Callable[..., object]
) -> None:
    """保持期間を過ぎたゴミ箱の要約だけが削除されることを確認するテスト.

    deleted_at が NULL のアクティブな要約は対象外. ここが壊れると使用中の要約が消える.
    """
    now = datetime.now(UTC)
    user = User(email="trash@example.com", name="Trash", status=UserStatus.approved)
    expired = _summary(user.id, deleted_at=now - timedelta(days=31))
    kept_trashed = _summary(user.id, deleted_at=now - timedelta(days=29))
    active = _summary(user.id)
    seed(user, expired, kept_trashed, active)

    purged = db_call(_purge)

    assert purged == _EXPECTED_PURGED
    remaining = {summary.id for summary in db_call(_all_summaries)}
    assert remaining == {kept_trashed.id, active.id}


def test_purge_cascades_to_child_rows(
    seed: Callable[..., None], db_call: Callable[..., object]
) -> None:
    """要約を消すと子行も一緒に消えることを確認するテスト.

    models に Relationship は無く DB の ON DELETE CASCADE だけが根拠なので実 DB で確認する.
    """
    now = datetime.now(UTC)
    user = User(email="trash@example.com", name="Trash", status=UserStatus.approved)
    expired = _summary(user.id, deleted_at=now - timedelta(days=31))
    kept = _summary(user.id)
    seed(
        user,
        expired,
        kept,
        Topic(summary_id=expired.id, title="議題", summary="要約"),
        Decision(summary_id=expired.id, description="決定"),
        ActionItem(summary_id=expired.id, description="宿題"),
        TranscriptSegment(
            summary_id=expired.id,
            rank="a0",
            speaker_label="Speaker 1",
            start_ms=0,
            end_ms=1000,
            text="発言",
        ),
        Topic(summary_id=kept.id, title="議題", summary="要約"),
    )

    db_call(_purge)

    assert db_call(_child_summary_ids) == {kept.id}


def test_purge_keeps_transcription_job_with_null_summary_id(
    seed: Callable[..., None], db_call: Callable[..., object]
) -> None:
    """要約を消してもジョブ行は残り summary_id だけ NULL になることを確認するテスト.

    transcription_jobs.summary_id は ON DELETE SET NULL なので, purge は FK 違反にならない.
    """
    now = datetime.now(UTC)
    user = User(email="trash@example.com", name="Trash", status=UserStatus.approved)
    expired = _summary(user.id, deleted_at=now - timedelta(days=31))
    job = TranscriptionJob(
        user_id=user.id,
        status=JobStatus.completed,
        filename="a.mp3",
        content_hash=uuid4().hex,
        media_key="uploads/job",
        summary_id=expired.id,
        completed_at=now,
    )
    seed(user, expired, job)

    db_call(_purge)

    assert [row.summary_id for row in db_call(_all_jobs)] == [None]


def test_purge_keeps_everything_within_retention(
    seed: Callable[..., None], db_call: Callable[..., object]
) -> None:
    """保持期間内の要約は 1 件も消えないことを確認するテスト."""
    now = datetime.now(UTC)
    user = User(email="trash@example.com", name="Trash", status=UserStatus.approved)
    fresh_trashed = _summary(user.id, deleted_at=now - timedelta(hours=1))
    active = _summary(user.id)
    seed(user, fresh_trashed, active)

    assert db_call(_purge) == 0
    assert len(db_call(_all_summaries)) == _EXPECTED_KEPT
