import asyncio
from unittest.mock import patch
from uuid import uuid4

from app.queue.tasks import (
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

        async def _touch(_session: object, job_id: object) -> None:
            await asyncio.sleep(0)  # 実際の DB 呼び出しと同じく制御を返す
            calls.append(job_id)
            if len(calls) == 1:
                msg = "db down"
                raise RuntimeError(msg)
            if len(calls) >= _EXPECTED_CALLS:
                reached.set()

        with (
            patch("app.queue.tasks.touch_job_heartbeat", new=_touch),
            patch("app.queue.tasks.async_session"),
        ):
            loop = asyncio.create_task(_heartbeat_loop(uuid4(), interval=0))
            try:
                await asyncio.wait_for(reached.wait(), timeout=2)
            finally:
                loop.cancel()

    asyncio.run(_run())

    assert len(calls) >= _EXPECTED_CALLS
