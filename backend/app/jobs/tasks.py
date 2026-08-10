from __future__ import annotations

import asyncio
from datetime import datetime
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from loguru import logger

from app.db.engine import async_session
from app.jobs.core import (
    MAX_ATTEMPTS,
    finish_ok,
    finish_retry,
    is_job_owner,
    touch_heartbeat,
)
from app.llm.summarize import summarize_chain
from app.settings.config import llm_semaphore
from app.stt.pipeline import cleanup_transcribe_job, transcribe_with_diarization
from app.summaries.core import create_summary

if TYPE_CHECKING:
    from uuid import UUID

    from sqlmodel.ext.asyncio.session import AsyncSession

    from app.db.models import TranscriptionJob
    from app.stt.types import Segment


_MEETING_TZ = ZoneInfo("Asia/Tokyo")
_HEARTBEAT_INTERVAL_SECONDS = 60


async def _heartbeat_loop(
    job_id: UUID, token: UUID, interval: int = _HEARTBEAT_INTERVAL_SECONDS
) -> None:
    """処理中の間, 定期的に生存を報告し続ける.

    Args:
        job_id (UUID): ジョブID
        token (UUID): このジョブを取得したときの owner_token
        interval (int, optional): 報告間隔(秒). Defaults to _HEARTBEAT_INTERVAL_SECONDS (60).
    """
    while True:
        await asyncio.sleep(interval)
        try:
            async with async_session() as hb_session:
                if not await touch_heartbeat(hb_session, job_id, token):
                    logger.warning(f"Job {job_id} was reclaimed, stopping heartbeat")
                    return
        except Exception as e:  # ruff:ignore[blind-except] - 一時的な DB エラーで孤児判定させない
            logger.warning(f"Heartbeat failed for job {job_id}: {e}")


def _ensure_segments(segments: list[Segment]) -> None:
    """空のセグメントは失敗として扱い, 例外で再試行させる.

    Args:
        segments (list[Segment]): STT が返した segment 列.

    Raises:
        ValueError: segments が空の場合.
    """
    if not segments:
        msg = "No segments were generated from the media"
        raise ValueError(msg)


async def _run_transcription_pipeline(
    db_session: AsyncSession, job: TranscriptionJob, token: UUID
) -> None:
    """STT -> 要約 -> summary 保存 -> completed の一連の処理を実行する.

    Args:
        db_session (AsyncSession): DBのセッション
        job (TranscriptionJob): 処理対象のジョブ
        token (UUID): このジョブを取得したときの owner_token
    """
    segments = await transcribe_with_diarization(job.media_key, job.num_speakers, job_id=job.id)
    _ensure_segments(segments)
    reference_date = job.recorded_at or datetime.now(_MEETING_TZ).date()
    async with llm_semaphore:
        if not await is_job_owner(db_session, job.id, token):
            logger.warning(f"Job {job.id} was reclaimed, aborting before LLM")
            return
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
    if not await finish_ok(db_session, job.id, token, summary.id):
        logger.warning(f"Job {job.id} was reclaimed, discarding result")
        return
    await cleanup_transcribe_job(job.id)


async def process_one_job(job: TranscriptionJob, token: UUID) -> None:
    """取得済みのジョブを STT -> 要約 -> completed まで処理する.

    Args:
        job (TranscriptionJob): fetch_one が取得したジョブ (processing 済み)
        token (UUID): fetch_one が発行した owner_token
    """
    async with async_session() as db_session:
        heartbeat = asyncio.create_task(_heartbeat_loop(job.id, token))
        try:
            await _run_transcription_pipeline(db_session, job, token)
        except Exception as e:  # ruff:ignore[blind-except] - 失敗を記録して次のジョブへ進む
            logger.exception(f"Failed job {job.id} (attempt {job.attempts}/{MAX_ATTEMPTS})")
            try:
                await db_session.rollback()
                await finish_retry(
                    db_session, job.id, token, error=type(e).__name__, attempts=job.attempts
                )
            except Exception as inner:  # ruff:ignore[blind-except]
                logger.error(f"Recovery failed for job {job.id}: {inner}")
        finally:
            heartbeat.cancel()
