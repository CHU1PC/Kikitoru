from __future__ import annotations

import asyncio
import contextlib
import signal
from typing import TYPE_CHECKING

from loguru import logger

from app.db.engine import async_session, engine
from app.db.models import JobStatus
from app.jobs.core import (
    fail_expired_jobs,
    fetch_one,
    purge_old,
    reclaim_orphans,
    release_claims,
)
from app.jobs.tasks import process_one_job
from app.settings import settings
from app.settings.job_queue import (
    COMPLETED_RETENTION_DAYS,
    FAILED_RETENTION_DAYS,
    ORPHAN_THRESHOLD_SECONDS,
    POLL_INTERVAL_SECONDS,
    PURGE_INTERVAL_SECONDS,
    RECLAIM_INTERVAL_SECONDS,
    SHUTDOWN_GRACE_SECONDS,
)
from app.settings.timeouts import MAX_RUNTIME_SECONDS
from app.storage import delete_object

if TYPE_CHECKING:
    from uuid import UUID

    from app.db.models import TranscriptionJob

# 実行中のジョブ (job_id -> owner_token). 停止時にまとめて pending へ戻す
_in_flight: dict[UUID, UUID] = {}


async def _sleep_or_stop(shutdown: asyncio.Event, seconds: float) -> None:
    """停止要求が来るまで最大 seconds 秒待つ.

    Args:
        shutdown (asyncio.Event): 停止要求のイベント
        seconds (float): 最大待機秒数
    """
    with contextlib.suppress(TimeoutError):
        await asyncio.wait_for(shutdown.wait(), timeout=seconds)


async def _claim_next() -> TranscriptionJob | None:
    """取得可能なジョブを1件だけ所有権つきで取り出す.

    Returns:
        TranscriptionJob | None: 取得したジョブ. なければ (または失敗したら) None
    """
    try:
        async with async_session() as db_session:
            return await fetch_one(db_session)
    except Exception as e:  # ruff:ignore[blind-except] - 一時的な DB エラーで lane を止めない
        logger.warning(f"fetch_one failed: {e}")
        return None


async def _lane(lane_id: int, shutdown: asyncio.Event) -> None:
    """1本の実行レーン. 取得 -> 処理 -> 取得 を停止要求まで繰り返す.

    Args:
        lane_id (int): レーン番号
        shutdown (asyncio.Event): 停止要求のイベント
    """
    await _sleep_or_stop(
        shutdown, POLL_INTERVAL_SECONDS * lane_id / settings.WORKER_CONCURRENT_LIMIT
    )
    while not shutdown.is_set():
        job = await _claim_next()
        if job is None:
            await _sleep_or_stop(shutdown, POLL_INTERVAL_SECONDS)
            continue
        token = job.owner_token
        if token is None:
            logger.error(f"Job {job.id} was fetched without an owner_token")
            continue
        _in_flight[job.id] = token
        try:
            await process_one_job(job, token)
        except Exception:  # ruff:ignore[blind-except] - 1件の失敗で lane を止めない
            logger.exception(f"lane {lane_id}: unhandled error for job {job.id}")
        finally:
            _in_flight.pop(job.id, None)


async def _reclaim_loop(shutdown: asyncio.Event) -> None:
    """詰まったジョブを定期的に直す. 時間切れの打ち切りと, 生存報告が途絶えた分の回収.

    Args:
        shutdown (asyncio.Event): 停止要求のイベント
    """
    while not shutdown.is_set():
        expired = reclaimed = 0
        try:
            async with async_session() as db_session:
                # 先に `fail_expired_jobs` を呼び出す. 逆順だと時間切れが pending に戻り, 次の周期まで生き延びる
                expired = await fail_expired_jobs(
                    db_session, max_runtime_seconds=MAX_RUNTIME_SECONDS
                )
                reclaimed = await reclaim_orphans(
                    db_session, older_than_seconds=ORPHAN_THRESHOLD_SECONDS
                )
        except Exception as e:  # ruff:ignore[blind-except] - 次の周期で再試行する
            logger.warning(f"reclaim loop failed: {e}")
        if expired:
            logger.warning(f"Timed out {expired} jobs over the runtime budget")
        if reclaimed:
            logger.warning(f"Reclaimed {reclaimed} orphaned jobs")
        await _sleep_or_stop(shutdown, RECLAIM_INTERVAL_SECONDS)


async def _delete_orphaned_media(purged: list[tuple[JobStatus, str]]) -> None:
    """削除したジョブのうち, 失敗した分の音声だけ S3 から消す.

    completed の音声は summaries が再生に使うので残す.

    Args:
        purged (list[tuple[JobStatus, str]]): 削除した行の (status, media_key)
    """
    for status, media_key in purged:
        if status is not JobStatus.failed:
            continue
        try:
            await delete_object(media_key)
        except Exception as e:  # ruff:ignore[blind-except] - 1件の失敗で残りを道連れにしない
            logger.error(f"Leaked S3 object {media_key} (purged row is already gone): {e}")


async def _purge_loop(shutdown: asyncio.Event) -> None:
    """保持期間を過ぎた終了済みジョブと, 失敗ジョブの音声を定期的に削除する.

    Args:
        shutdown (asyncio.Event): 停止要求のイベント
    """
    while not shutdown.is_set():
        try:
            async with async_session() as db_session:
                purged = await purge_old(
                    db_session,
                    completed_days=COMPLETED_RETENTION_DAYS,
                    failed_days=FAILED_RETENTION_DAYS,
                )
            await _delete_orphaned_media(purged)
            if purged:
                logger.info(f"Purged {len(purged)} finished jobs")
        except Exception as e:  # ruff:ignore[blind-except] - 次の周期で再試行する
            logger.warning(f"purge_old failed: {e}")
        await _sleep_or_stop(shutdown, PURGE_INTERVAL_SECONDS)


async def _release_in_flight() -> None:
    """停止時に抱えているジョブを pending に戻し, 次の worker がすぐ拾えるようにする."""
    tokens = list(_in_flight.values())
    if not tokens:
        return
    try:
        async with async_session() as db_session:
            released = await release_claims(db_session, tokens)
    except Exception as e:  # ruff:ignore[blind-except] - 停止処理を例外で止めない
        logger.error(f"Failed to release in-flight jobs: {e}")
        return
    logger.info(f"Released {released} in-flight jobs on shutdown")


async def main() -> None:
    """Worker の入口. lane と定期処理を起動し, SIGTERM/SIGINT で停止する."""
    shutdown = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, shutdown.set)

    lanes = settings.WORKER_CONCURRENT_LIMIT
    logger.info(f"Worker started: {lanes} lanes, poll {POLL_INTERVAL_SECONDS}s")
    tasks = [asyncio.create_task(_lane(i, shutdown), name=f"lane-{i}") for i in range(lanes)]
    tasks += [
        asyncio.create_task(_reclaim_loop(shutdown), name="reclaim"),
        asyncio.create_task(_purge_loop(shutdown), name="purge"),
    ]

    await shutdown.wait()
    logger.info("Shutdown requested, waiting for in-flight jobs")
    _, pending = await asyncio.wait(tasks, timeout=SHUTDOWN_GRACE_SECONDS)
    if pending:
        # cancel 後の finally は完走が保証できないので, 生きているうちに所有権を返す
        await _release_in_flight()
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
    await engine.dispose()
    logger.info("Worker stopped")


if __name__ == "__main__":
    asyncio.run(main())
