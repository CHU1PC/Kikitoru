from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.audio.orphans import OrphanScanAbortedError, find_orphan_media
from app.db.models import JobStatus, Summary, TranscriptionJob, User, UserStatus

if TYPE_CHECKING:
    from collections.abc import Callable
    from contextlib import AbstractContextManager
    from uuid import UUID

    from sqlmodel.ext.asyncio.session import AsyncSession

_MIN_AGE_SECONDS = 24 * 60 * 60
_KEPT = "uploads/kept"
_GONE = "uploads/gone"


def _old() -> datetime:
    """最低年齢を満たす最終更新時刻を返す.

    Returns:
        datetime: 現在から十分に過去の時刻.
    """
    return datetime.now(UTC) - timedelta(seconds=_MIN_AGE_SECONDS * 2)


def _on_s3(**keys: datetime) -> AbstractContextManager[object]:
    """S3 の列挙結果を差し替える.

    Args:
        **keys (datetime): key の末尾 -> 最終更新時刻.

    Returns:
        AbstractContextManager[object]: 差し替えを行う context manager.
    """
    listed = {f"uploads/{name}": modified for name, modified in keys.items()}
    return patch("app.audio.orphans.list_upload_keys", new=AsyncMock(return_value=listed))


def _job(user_id: UUID, media_key: str) -> TranscriptionJob:
    """指定の media_key を持つジョブを組み立てる (保存はしない).

    Args:
        user_id (UUID): 所有者のユーザー ID.
        media_key (str): 参照する S3 キー.

    Returns:
        TranscriptionJob: 組み立てたジョブ.
    """
    return TranscriptionJob(
        user_id=user_id,
        status=JobStatus.pending,
        filename="a.mp3",
        content_hash=uuid4().hex,
        media_key=media_key,
    )


def _summary(user_id: UUID, media_key: str | None) -> Summary:
    """指定の media_key を持つ要約を組み立てる (保存はしない).

    Args:
        user_id (UUID): 所有者のユーザー ID.
        media_key (str | None): 参照する S3 キー. 音声が無いなら None.

    Returns:
        Summary: 組み立てた要約.
    """
    return Summary(user_id=user_id, filename="a.mp3", overall_summary="x", media_key=media_key)


def _find(db_session: AsyncSession) -> object:
    """既定の最低年齢で find_orphan_media を呼ぶ.

    Args:
        db_session (AsyncSession): DB セッション.

    Returns:
        object: 孤児と判定した key のリスト.
    """
    return find_orphan_media(db_session, min_age_seconds=_MIN_AGE_SECONDS)


def _user(email: str) -> User:
    """承認済みユーザーを組み立てる (保存はしない).

    Args:
        email (str): メールアドレス.

    Returns:
        User: 組み立てたユーザー.
    """
    return User(email=email, name="Orphan", status=UserStatus.approved)


def test_object_referenced_by_a_job_is_kept(
    seed: Callable[..., None], db_call: Callable[..., object]
) -> None:
    """ジョブが参照する key を残し, 参照の無い key だけを孤児にすることを確認するテスト.

    参照側を1件も返さないだけの実装で通らないよう, 孤児が実際に出ることも同時に見る.
    """
    user = _user("job-ref@example.com")
    seed(user, _job(user.id, _KEPT))

    with _on_s3(kept=_old(), gone=_old()):
        assert db_call(_find) == [_GONE]


def test_object_referenced_by_a_summary_is_kept(
    seed: Callable[..., None], db_call: Callable[..., object]
) -> None:
    """要約が参照する key を残すことを確認するテスト.

    ジョブ行は完了 7 日後に消えるので, 要約側を見ないと生きている音声を消す.
    """
    user = _user("summary-ref@example.com")
    seed(user, _summary(user.id, _KEPT), _summary(user.id, None))

    with _on_s3(kept=_old(), gone=_old()):
        assert db_call(_find) == [_GONE]


def test_recent_object_is_not_an_orphan(
    seed: Callable[..., None], db_call: Callable[..., object]
) -> None:
    """最低年齢に満たない key を対象外にすることを確認するテスト.

    S3 に置いてから DB 行が commit されるまでの窓を跨いで消さないため.
    """
    user = _user("recent@example.com")
    seed(user, _job(user.id, _KEPT))

    with _on_s3(kept=_old(), gone=datetime.now(UTC)):
        assert db_call(_find) == []


def test_scan_aborts_when_too_many_look_orphaned(
    seed: Callable[..., None], db_call: Callable[..., object]
) -> None:
    """孤児が多すぎるときに判定ごと放棄することを確認するテスト.

    参照が部分的にしか無い DB (リストア直後, 接続先違い) を全件削除と区別できない.
    """
    user = _user("too-many@example.com")
    seed(user, _job(user.id, _KEPT))
    listed = {"kept": _old()} | {f"gone-{i}": _old() for i in range(20)}

    with _on_s3(**listed), pytest.raises(OrphanScanAbortedError, match="too many"):
        db_call(_find)


def test_scan_aborts_when_nothing_is_referenced(
    db_call: Callable[..., object],
) -> None:
    """参照が1件も無いときに判定ごと放棄することを確認するテスト.

    DB 未 migration や接続先違いを全件削除と区別できないので, 安全側に倒す.
    """
    with _on_s3(kept=_old(), gone=_old()), pytest.raises(OrphanScanAbortedError):
        db_call(_find)
