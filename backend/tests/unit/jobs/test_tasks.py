import asyncio
from unittest.mock import patch
from uuid import uuid4

from app.jobs.tasks import (
    _heartbeat_loop,  # pyright: ignore[reportPrivateUsage]  # ruff:ignore[import-private-name]
)

_EXPECTED_CALLS = 3


def test_heartbeat_loop_survives_db_error() -> None:
    """DB エラーが起きても生存報告のループが止まらないことを確認するテスト.

    ここが止まると健全なジョブが孤児と誤判定されるため, 例外を握って継続する必要がある.
    """
    calls: list[object] = []

    async def _run() -> None:
        reached = asyncio.Event()

        async def _touch(_session: object, job_id: object, _token: object) -> bool:
            await asyncio.sleep(0)  # 実際の DB 呼び出しと同じく制御を返す
            calls.append(job_id)
            if len(calls) == 1:
                msg = "db down"
                raise RuntimeError(msg)
            if len(calls) >= _EXPECTED_CALLS:
                reached.set()
            return True

        with (
            patch("app.jobs.tasks.touch_heartbeat", new=_touch),
            patch("app.jobs.tasks.async_session"),
        ):
            loop = asyncio.create_task(_heartbeat_loop(uuid4(), uuid4(), interval=0))
            try:
                await asyncio.wait_for(reached.wait(), timeout=2)
            finally:
                loop.cancel()

    asyncio.run(_run())

    assert len(calls) >= _EXPECTED_CALLS


def test_heartbeat_loop_stops_when_ownership_is_lost() -> None:
    """所有権を失ったら生存報告を止めることを確認するテスト.

    報告を続けると新しい所有者の行が生き続けているように見え, 孤児検出が効かなくなる.
    """
    calls: list[object] = []

    async def _run() -> None:
        async def _touch(_session: object, job_id: object, _token: object) -> bool:
            await asyncio.sleep(0)
            calls.append(job_id)
            return False  # 回収されて token が一致しなくなった状態

        with (
            patch("app.jobs.tasks.touch_heartbeat", new=_touch),
            patch("app.jobs.tasks.async_session"),
        ):
            await asyncio.wait_for(_heartbeat_loop(uuid4(), uuid4(), interval=0), timeout=2)

    asyncio.run(_run())

    assert len(calls) == 1  # 1 回目の False で抜ける
