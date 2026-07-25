from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from loguru import logger
from procrastinate import RetryStrategy

from app.db.engine import async_session
from app.db.models import JobStatus
from app.db.summaries import create_summary
from app.db.transcription_jobs import get_owned_job, mark_completed, mark_failed
from app.llm.summarize import summarize_chain
from app.queue.app import queue_app
from app.settings.config import llm_semaphore
from app.stt.pipeline import transcribe_with_diarization

_MEETING_TZ = ZoneInfo("Asia/Tokyo")

if TYPE_CHECKING:
    from uuid import UUID

    from sqlmodel.ext.asyncio.session import AsyncSession

    from app.db.models import TranscriptionJob
    from app.stt.types import Segment


def _ensure_segments(segments: list[Segment]) -> None:
    """空のセグメントは task 失敗として扱う. procrastinate retry を発動させる.

    Args:
        segments (list[Segment]): STT が返した segment 列.

    Raises:
        ValueError: segments が空の場合.
    """
    if not segments:
        msg = "No segments were generated from the media"
        raise ValueError(msg)


async def _run_transcription_pipeline(db_session: AsyncSession, job: TranscriptionJob) -> None:
    """STT -> 要約 -> summary 保存 -> completed の一連の処理を実行する.

    Args:
        db_session (AsyncSession): DBのセッション
        job (TranscriptionJob): 処理対象のジョブ
    """
    segments = await transcribe_with_diarization(job.media_key, job.num_speakers)
    _ensure_segments(segments)
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


@queue_app.task(
    name="process_transcription_job",
    queue="stt",
    retry=RetryStrategy(max_attempts=3, exponential_wait=60),
)
async def process_transcription_job(job_id: UUID, user_id: UUID) -> None:
    """1件の TranscriptionJob を STT -> 要約 -> completed まで処理する task.

    Args:
        job_id (UUID): TranscriptionJob の ID
        user_id (UUID): User の ID
    """
    async with async_session() as db_session:
        job = await get_owned_job(db_session, user_id, job_id)
        if job is None:  # get_owned_job が Job を取得できなかった時
            logger.error(f"Task called for non-existent job {job_id}")
            return
        if job.status in {JobStatus.completed, JobStatus.failed}:  # すでに Job が完了しているもしくは失敗した場合
            logger.warning(f"Task called for job {job_id} with status {job.status}")
            return

        job.status = JobStatus.processing
        job.started_at = datetime.now(_MEETING_TZ)
        db_session.add(job)
        await db_session.commit()

        try:
            await _run_transcription_pipeline(db_session, job)
        except Exception as e:
            logger.error(f"Failed job {job.id}: {e}")
            await db_session.rollback()
            await db_session.refresh(job)  # rollback 後の in-memory は使えないので DB から読み直す
            await mark_failed(db_session, job, str(e))
            raise
