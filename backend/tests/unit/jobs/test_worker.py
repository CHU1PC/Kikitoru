import asyncio
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from app.db.models import JobStatus
from app.jobs.worker import (
    _delete_orphaned_media,  # pyright: ignore[reportPrivateUsage]  # ruff:ignore[import-private-name]
    _lane,  # pyright: ignore[reportPrivateUsage]  # ruff:ignore[import-private-name]
    _sleep_or_stop,  # pyright: ignore[reportPrivateUsage]  # ruff:ignore[import-private-name]
)

_EXPECTED_CLAIMS = 2


def test_sleep_or_stop_returns_immediately_when_shutdown_is_set() -> None:
    """停止要求が立っていれば長い待機時間でも即座に抜けることを確認するテスト.

    ここが効かないと purge の 1 時間待ちで停止が間に合わず SIGKILL される.
    """

    async def _run() -> None:
        shutdown = asyncio.Event()
        shutdown.set()
        await asyncio.wait_for(_sleep_or_stop(shutdown, 3600), timeout=1)

    asyncio.run(_run())  # timeout せずに終われば成功


def test_sleep_or_stop_wakes_when_shutdown_is_set_while_waiting() -> None:
    """待機中に停止要求が来たら即座に抜けることを確認するテスト."""

    async def _run() -> None:
        shutdown = asyncio.Event()
        waiter = asyncio.create_task(_sleep_or_stop(shutdown, 3600))
        await asyncio.sleep(0)
        shutdown.set()
        await asyncio.wait_for(waiter, timeout=1)

    asyncio.run(_run())


def test_lane_survives_a_failing_job() -> None:
    """1件の処理が例外で落ちても lane が次のジョブを取りに行くことを確認するテスト.

    例外を漏らすと lane が死に, 再起動するまで処理能力が戻らない.
    """
    claimed: list[object] = []

    async def _run() -> None:
        shutdown = asyncio.Event()

        async def _claim() -> object:
            await asyncio.sleep(0)  # 実際の DB 呼び出しと同じく制御を返す
            if len(claimed) >= _EXPECTED_CLAIMS:
                shutdown.set()
                return None
            job = SimpleNamespace(id=uuid4(), owner_token=uuid4())
            claimed.append(job)
            return job

        async def _process(_job: object, _token: object) -> None:
            await asyncio.sleep(0)
            msg = "boom"
            raise RuntimeError(msg)

        with (
            patch("app.jobs.worker._claim_next", new=_claim),
            patch("app.jobs.worker.process_one_job", new=_process),
        ):
            await asyncio.wait_for(_lane(0, shutdown), timeout=2)

    asyncio.run(_run())

    assert len(claimed) == _EXPECTED_CLAIMS  # 1件目が失敗しても 2件目を取りに行った


def test_delete_orphaned_media_continues_after_a_failure() -> None:
    """1件の S3 削除が失敗しても残りを試すことを確認するテスト.

    purge_old が commit した後なので行は既に無く, 中断すると残りは永久に回収できない.
    """
    deleted: list[str] = []

    async def _delete(key: str) -> None:
        await asyncio.sleep(0)
        deleted.append(key)
        if key == "uploads/boom":
            msg = "s3 down"
            raise RuntimeError(msg)

    purged = [
        (JobStatus.failed, "uploads/boom"),
        (JobStatus.completed, "uploads/keep"),  # completed は消さない
        (JobStatus.failed, "uploads/after"),
    ]

    with patch("app.jobs.worker.delete_object", new=_delete):
        asyncio.run(_delete_orphaned_media(purged))

    assert deleted == ["uploads/boom", "uploads/after"]


def test_lane_exits_on_shutdown() -> None:
    """停止要求でレーンがループを抜けることを確認するテスト."""

    async def _run() -> None:
        shutdown = asyncio.Event()

        async def _claim() -> None:
            await asyncio.sleep(0)

        with patch("app.jobs.worker._claim_next", new=_claim):
            lane = asyncio.create_task(_lane(0, shutdown))
            await asyncio.sleep(0)
            shutdown.set()
            await asyncio.wait_for(lane, timeout=2)

    asyncio.run(_run())
