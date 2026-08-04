from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID
from zoneinfo import ZoneInfo

from loguru import logger
from procrastinate import RetryStrategy

from app.db.engine import async_session
from app.db.models import JobStatus
from app.db.summaries import create_summary
from app.db.transcription_jobs import (
    claim_job_ownership,
    clear_job_ownership,
    find_orphaned_processing_jobs,
    get_owned_job,
    is_job_owner,
    mark_completed,
    mark_failed,
    touch_job_heartbeat,
)
from app.llm.summarize import summarize_chain
from app.queue.app import queue_app
from app.settings.config import llm_semaphore
from app.stt.pipeline import cleanup_transcribe_job, transcribe_with_diarization

_MEETING_TZ = ZoneInfo("Asia/Tokyo")
_MAX_RETRIES = 3
_HEARTBEAT_INTERVAL_SECONDS = 60

# 生存報告がこの秒数途絶えたら孤児とみなす. retry の backoff (最大 180 秒) を上回る必要がある
_ORPHAN_THRESHOLD_SECONDS = 10 * 60

if TYPE_CHECKING:

    from procrastinate import JobContext
    from sqlmodel.ext.asyncio.session import AsyncSession

    from app.db.models import TranscriptionJob
    from app.stt.types import Segment


async def _heartbeat_loop(job_id: UUID, interval: int = _HEARTBEAT_INTERVAL_SECONDS) -> None:
    """処理中の間, 定期的に生存を報告し続ける.

    一時的な DB エラーでループが止まると健全なジョブが孤児判定されるため, 例外は握って継続する.

    Args:
        job_id (UUID): ジョブID
        interval (int, optional): 報告間隔(秒). Defaults to _HEARTBEAT_INTERVAL_SECONDS (60).
    """
    while True:
        await asyncio.sleep(interval)
        try:
            async with async_session() as hb_session:
                await touch_job_heartbeat(hb_session, job_id)
        except Exception as e:  # ruff:ignore[blind-except] - 一度の失敗でループを止めない
            logger.warning(f"Heartbeat failed for job {job_id}: {e}")


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


async def _run_transcription_pipeline(db_session: AsyncSession, job: TranscriptionJob, attempt: int) -> None:
    """STT -> 要約 -> summary 保存 -> completed の一連の処理を実行する.

    LLM 呼び出し直前に所有権を再検査し, 失っていれば何もせず戻る (勝者の状態を壊さない).

    Args:
        db_session (AsyncSession): DBのセッション
        job (TranscriptionJob): 処理対象のジョブ
        attempt (int): このタスクが所有権を取った attempt 番号
    """
    segments = await transcribe_with_diarization(job.media_key, job.num_speakers, job_id=job.id)
    _ensure_segments(segments)
    reference_date = job.recorded_at or datetime.now(_MEETING_TZ).date()
    async with llm_semaphore:
        if not await is_job_owner(db_session, job.id, attempt):
            logger.warning(f"Job {job.id} was reclaimed by a newer attempt, aborting before LLM")
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
    await mark_completed(db_session, job, summary.id)
    await cleanup_transcribe_job(job.id)


@queue_app.task(
    name="process_transcription_job",
    queue="stt",
    retry=RetryStrategy(max_attempts=_MAX_RETRIES, linear_wait=60),
    pass_context=True,
)
async def process_transcription_job(context: JobContext, job_id: str, user_id: str) -> None:
    """1件の TranscriptionJob を STT -> 要約 -> completed まで処理する task.

    Args:
        context (JobContext): procrastinate 実行時 context. attempts を retry 判定に使う
        job_id (str): TranscriptionJob の ID
        user_id (str): User の ID
    """
    async with async_session() as db_session:
        job = await get_owned_job(db_session, UUID(user_id), UUID(job_id))
        if job is None:  # get_owned_job が Job を取得できなかった時
            logger.error(f"Task called for non-existent job {job_id}")
            return
        if job.status in {JobStatus.completed, JobStatus.failed}:
            logger.warning(f"Task called for job {job_id} with status {job.status}")
            return

        attempt = context.job.attempts
        if not await claim_job_ownership(db_session, job.id, attempt):
            logger.warning(f"Job {job_id} is owned by a newer attempt, skipping")
            return

        job.status = JobStatus.processing
        job.heartbeat_at = datetime.now(UTC)
        if attempt == 0:
            job.started_at = datetime.now(UTC)
        db_session.add(job)
        await db_session.commit()

        heartbeat = asyncio.create_task(_heartbeat_loop(job.id))
        try:
            await _run_transcription_pipeline(db_session, job, attempt)
        except Exception as e:
            logger.exception(f"Failed job {job.id} (attempt {context.job.attempts + 1}/{_MAX_RETRIES + 1})")
            try:
                await db_session.rollback()
                await db_session.refresh(job)  # rollback 後の in-memory は使えないので DB から読み直す
                is_final = context.job.attempts >= _MAX_RETRIES
                await mark_failed(db_session, job, type(e).__name__, is_final=is_final)
            except Exception as inner:  # ruff:ignore[blind-except]
                logger.error(f"Recovery failed for job {job.id}: {inner}")
            raise
        finally:
            heartbeat.cancel()


@queue_app.periodic(cron="*/5 * * * *", periodic_id="reclaim_stalled_stt_jobs")
@queue_app.task(
    name="reclaim_stalled_stt_jobs",
    queue="stt",
    pass_context=True,
)
async def reclaim_stalled_stt_jobs(
    context: JobContext,
    timestamp: int,  # ruff: ignore[unused-function-argument]
) -> None:
    """Stalled procrastinate job (worker が SIGKILL 等で消えた孤児) を retry queue に戻す.

    Args:
        context (JobContext): procrastinate 実行時 context.
        timestamp (int): periodic scheduler が渡す実行予定時刻.
    """
    stalled = list(await context.app.job_manager.get_stalled_jobs(queue="stt"))
    if not stalled:
        return
    now = datetime.now(UTC)
    for job in stalled:
        if job.id is not None:
            await context.app.job_manager.retry_job_by_id_async(job.id, retry_at=now)
    logger.info(f"Reclaimed {len(stalled)} stalled stt jobs")


@queue_app.periodic(cron="*/10 * * * *", periodic_id="requeue_orphaned_jobs")
@queue_app.task(
    name="requeue_orphaned_jobs",
    queue="stt",
    pass_context=True,
)
async def requeue_orphaned_jobs(
    context: JobContext,  # ruff: ignore[unused-function-argument]
    timestamp: int,  # ruff: ignore[unused-function-argument]
) -> None:
    """キュー行が消えて回収されなくなったジョブを再投入する.

    reclaim_stalled_stt_jobs は procrastinate 側を見るため, ジョブ行自体が削除されると
    検出できない. 自前の transcription_jobs を正として時間で検出する最終手段.

    Args:
        context (JobContext): procrastinate 実行時 context.
        timestamp (int): periodic scheduler が渡す実行予定時刻.
    """
    async with async_session() as db_session:
        orphaned = await find_orphaned_processing_jobs(
            db_session, older_than_seconds=_ORPHAN_THRESHOLD_SECONDS
        )
        if not orphaned:
            return
        for job in orphaned:
            await clear_job_ownership(db_session, job.id)
            await process_transcription_job.configure(
                queueing_lock=f"stt:{job.user_id}:{job.content_hash}",
                lock=f"stt:{job.id}",
            ).defer_async(job_id=str(job.id), user_id=str(job.user_id))
        logger.warning(f"Requeued {len(orphaned)} orphaned jobs")
