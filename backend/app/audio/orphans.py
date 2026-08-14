from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlmodel import col, select

from app.db.models import Summary, TranscriptionJob
from app.settings.storage import ORPHAN_MEDIA_ABORT_MIN_COUNT, ORPHAN_MEDIA_ABORT_RATIO
from app.storage import list_upload_keys

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession


class OrphanScanAbortedError(RuntimeError):
    """DB 側を信用できないため回収を打ち切ったときに送出される."""


async def _referenced_media_keys(db_session: AsyncSession) -> set[str]:
    """DB から参照されている media_key の集合を返す.

    Args:
        db_session (AsyncSession): DBセッション

    Returns:
        set[str]: transcription_jobs と summaries が参照している media_key の和集合
    """
    jobs = await db_session.exec(select(col(TranscriptionJob.media_key)))
    summaries = await db_session.exec(select(col(Summary.media_key)))
    return set(jobs.all()) | {media_key for media_key in summaries.all() if media_key is not None}


async def find_orphan_media(db_session: AsyncSession, *, min_age_seconds: int) -> list[str]:
    """DB から参照されていない uploads/ の key を返す.

    Args:
        db_session (AsyncSession): DBセッション
        min_age_seconds (int): これより新しいオブジェクトは対象外にする

    Returns:
        list[str]: 孤児と判定した key

    Raises:
        OrphanScanAbortedError: 参照が1件も無い場合と, 孤児が多すぎて DB 側を信用できない場合
    """
    # S3 を先に見る. 逆順だと, 間に commit されたジョブの音声を孤児と誤判定する
    on_s3 = await list_upload_keys()
    if not on_s3:
        return []

    referenced = await _referenced_media_keys(db_session)
    if not referenced:
        msg = f"Found {len(on_s3)} objects on S3 but no media_key in the database"
        raise OrphanScanAbortedError(msg)

    cutoff = datetime.now(UTC) - timedelta(seconds=min_age_seconds)
    orphans = sorted(key for key in on_s3.keys() - referenced if on_s3[key] < cutoff)
    too_many = len(orphans) > len(on_s3) * ORPHAN_MEDIA_ABORT_RATIO
    if len(orphans) > ORPHAN_MEDIA_ABORT_MIN_COUNT and too_many:
        msg = f"{len(orphans)} of {len(on_s3)} objects look orphaned, which is too many to trust"
        raise OrphanScanAbortedError(msg)
    return orphans
