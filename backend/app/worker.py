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
from app.settings.config import llm_semaphore
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


async def run_worker() -> None:
    """Pending ジョブを1件ずつ処理し続ける poling loop.

    起動時に stale ジョブを pending に戻し, その後は pending ジョブがあれば処理し, なければスリープする.
    """
    async with async_session() as db_session:
        reclaimed = await reclaim_stale_jobs(db_session)
    if reclaimed:
        logger.info(f"Reclaimed {reclaimed} stale jobs")
    logger.info("Worker started")

    while True:
        async with async_session() as db_session:
            job = await claim_next_job(db_session)
            if job is None:
                await asyncio.sleep(_IDLE_SLEEP_SECONDS)
                continue
            logger.info(f"Claimed job {job.id} for processing")
            try:
                await _process_job(db_session, job)
                logger.info(f"Job {job.id} completed successfully")
            except Exception as e:  # noqa: BLE001 - どのジョブ失敗でもループは止めない
                logger.error(f"Failed to process job {job.id}: {e}")
                try:
                    await mark_failed(db_session, job, str(e))
                except Exception as inner:  # noqa: BLE001 - どのジョブ失敗でもループは止めない
                    logger.error(f"Failed to mark job {job.id} as failed: {inner}")


def main() -> None:
    """Worker を起動する."""
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
