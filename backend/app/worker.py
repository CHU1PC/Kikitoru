from __future__ import annotations

import asyncio
from datetime import datetime
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from loguru import logger

from app.db.engine import async_session
from app.db.summaries import create_summary
from app.db.transcription_jobs import (
    claim_next_job,
    mark_completed,
    mark_failed,
    reclaim_stale_jobs,
)
from app.llm.summarize import summarize_chain
from app.settings.config import llm_semaphore, settings
from app.stt.pipeline import transcribe_with_diarization

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession

    from app.db.models import TranscriptionJob


_MEETING_TZ = ZoneInfo("Asia/Tokyo")
_IDLE_SLEEP_SECONDS = 5


async def _process_job(db_session: AsyncSession, job: TranscriptionJob) -> None:
    """1件のジョブを STT -> 要約 -> create_summary -> completed まで処理する.

    Args:
        db_session (AsyncSession): DBセッション
        job (TranscriptionJob): 処理対象のジョブ

    Raises:
        ValueError: STT でセグメントが生成されなかった場合
    """
    segments = await transcribe_with_diarization(job.media_key, job.num_speakers)
    if not segments:
        msg = "No segments were generated from the media"
        raise ValueError(msg)
    reference_date = job.recorded_at or datetime.now(_MEETING_TZ).date()
    async with llm_semaphore:
        llm_result = await summarize_chain.ainvoke((segments, reference_date))
    summary = await create_summary(
        db_session,
        job.user_id,
        job.filename,
        job.content_hash,
        llm_result,
        segments,
        job.media_key
    )
    await mark_completed(db_session, job, summary.id)


async def _process_and_handle(db_session: AsyncSession, job: TranscriptionJob, lane: int) -> None:
    """1件のジョブを処理し、失敗時は mark_failed で吸収する(ループを止めない).

    Args:
        db_session (AsyncSession): DBセッション
        job (TranscriptionJob): 処理対象のジョブ
        lane (int): ワーカーのレーン番号 (ログ出力用)
    """
    logger.info(f"[lane {lane}] Claimed job {job.id}")
    try:
        await _process_job(db_session, job)
        logger.info(f"[lane {lane}] Job {job.id} completed")
    except Exception as e:  # ruff:ignore[blind-except]
        logger.error(f"[lane {lane}] Failed job {job.id}: {e}")
        try:
            await db_session.rollback()
            await db_session.refresh(job)
            await mark_failed(db_session, job, str(e))
        except Exception as inner:  # ruff:ignore[blind-except]
            logger.error(f"[lane {lane}] mark_failed も失敗 {job.id}: {inner} (stale reclaim で回収)")


async def _worker_loop(lane: int) -> None:
    """Pending を1件ずつ claim して処理し続ける無限ループ(1レーン分).

    Args:
        lane (int): ワーカーのレーン番号 (ログ出力用)
    """
    while True:
        async with async_session() as db_session:
            job = await claim_next_job(db_session)
            if job is None:
                await asyncio.sleep(_IDLE_SLEEP_SECONDS)
                continue
            await _process_and_handle(db_session, job, lane)


async def _reclaim_loop(interval_seconds: int = 600) -> None:
    """処理中のまま放置されたジョブを定期的に pending へ戻し続ける常駐ループ.

    worker がジョブ処理の途中でクラッシュすると、そのジョブは processing の
    まま誰にも拾われずに残る. これを interval_seconds ごとに検出して pending
    へ戻し、別のレーンが処理し直せるようにする.

    Args:
        interval_seconds (int, optional): reclaim を走らせる間隔(秒). Defaults to 600.
    """
    while True:
        await asyncio.sleep(interval_seconds)  # 起動時 reclaim 済みなので先に sleep
        try:
            async with async_session() as db_session:
                reclaimed = await reclaim_stale_jobs(db_session)
            if reclaimed:
                logger.info(f"Periodic reclaim: {reclaimed} stale jobs")
        except Exception as e:  # ruff:ignore[blind-except] - reclaim 失敗で worker を止めない
            logger.error(f"Periodic reclaim failed: {e}")


async def run_worker() -> None:
    """Pending ジョブを1件ずつ処理し続ける poling loop.

    起動時に stale ジョブを pending に戻し, その後は pending ジョブがあれば処理し, なければスリープする.
    """
    async with async_session() as db_session:
        reclaimed = await reclaim_stale_jobs(db_session)
    if reclaimed:
        logger.info(f"Reclaimed {reclaimed} stale jobs")
    logger.info(f"Worker started with concurrency={settings.WORKER_CONCURRENT_LIMIT}")
    async with asyncio.TaskGroup() as tg:
        tg.create_task(_reclaim_loop())
        for lane in range(settings.WORKER_CONCURRENT_LIMIT):
            tg.create_task(_worker_loop(lane))


def main() -> None:
    """Worker を起動する."""
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
