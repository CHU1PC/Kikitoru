import asyncio
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from app.jobs.worker import (
    _lane,  # pyright: ignore[reportPrivateUsage]  # ruff:ignore[import-private-name]
    _orphan_media_loop,  # pyright: ignore[reportPrivateUsage]  # ruff:ignore[import-private-name]
    _sleep_or_stop,  # pyright: ignore[reportPrivateUsage]  # ruff:ignore[import-private-name]
    _sweep_orphan_media,  # pyright: ignore[reportPrivateUsage]  # ruff:ignore[import-private-name]
)

_EXPECTED_CLAIMS = 2


def _sweep(orphans: list[str], *, failing: str | None = None, stopped: bool = False) -> list[str]:
    """_sweep_orphan_media を回し, 消しに行った key を返す.

    Args:
        orphans (list[str]): 孤児として渡す key.
        failing (str | None): 削除が例外を投げる key.
        stopped (bool): 停止要求を立てた状態で呼ぶか.

    Returns:
        list[str]: delete_object に渡された key.
    """
    deleted: list[str] = []

    async def _delete(key: str) -> None:
        await asyncio.sleep(0)
        deleted.append(key)
        if key == failing:
            msg = "s3 down"
            raise RuntimeError(msg)

    async def _run() -> None:
        shutdown = asyncio.Event()
        if stopped:
            shutdown.set()
        await _sweep_orphan_media(orphans, shutdown)

    with patch("app.jobs.worker.delete_object", new=_delete):
        asyncio.run(_run())
    return deleted


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


def test_sweep_orphan_media_deletes_every_orphan() -> None:
    """渡された孤児をすべて消しに行くことを確認するテスト."""
    deleted = _sweep(["uploads/a", "uploads/b"])

    assert deleted == ["uploads/a", "uploads/b"]


def test_sweep_orphan_media_continues_after_a_failure() -> None:
    """1件の S3 削除が失敗しても残りを試すことを確認するテスト.

    中断すると, 残りは次の掃除まで丸1日 S3 に残り続ける.
    """
    deleted = _sweep(["uploads/boom", "uploads/after"], failing="uploads/boom")

    assert deleted == ["uploads/boom", "uploads/after"]


def test_sweep_orphan_media_stops_on_shutdown() -> None:
    """停止要求が立っていたら1件も消さないことを確認するテスト.

    掃除は冪等なので, 停止を待たせてまで消し切る理由がない.
    """
    deleted = _sweep(["uploads/a", "uploads/b"], stopped=True)

    assert deleted == []


def test_sweep_orphan_media_refuses_keys_outside_the_upload_prefix() -> None:
    """uploads/ の外の key を消しに行かないことを確認するテスト.

    取り消せない操作なので, 列挙側の prefix 指定だけに頼らない.
    """
    deleted = _sweep(["transcripts/x.json", "uploads/ok"])

    assert deleted == ["uploads/ok"]


def test_orphan_media_loop_waits_before_the_first_scan() -> None:
    """起動直後に走査しないことを確認するテスト.

    削除は取り消せないので, deploy や再起動ループのたびに実行させない.
    """
    scanned: list[object] = []

    async def _find(*_args: object, **_kwargs: object) -> list[str]:
        await asyncio.sleep(0)
        scanned.append(None)
        return []

    async def _run() -> None:
        shutdown = asyncio.Event()
        loop = asyncio.create_task(_orphan_media_loop(shutdown))
        await asyncio.sleep(0.05)  # 走査が起きるなら, この間に 1 回目が走る
        shutdown.set()
        await asyncio.wait_for(loop, timeout=2)

    with patch("app.jobs.worker.find_orphan_media", new=_find):
        asyncio.run(_run())

    assert scanned == []


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
