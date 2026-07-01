from __future__ import annotations

from typing import TYPE_CHECKING

from fractional_indexing import generate_key_between
from sqlmodel import col, select, update

from app.db.models import TranscriptSegment
from app.db.summaries import get_owned_summary

if TYPE_CHECKING:
    from uuid import UUID

    from sqlmodel.ext.asyncio.session import AsyncSession

    from app.schema.summaries import TranscriptSegmentCreate, TranscriptSegmentEdit, TranscriptSegmentSplit


async def load_owned_segment(
    db_session: AsyncSession,
    user_id: UUID,
    summary_id: UUID,
    segment_id: int
) -> TranscriptSegment | None:
    """親 summary の所有を確認した上で, transcript segment を取得する.

    Args:
        db_session (AsyncSession): データベースセッション
        user_id (UUID): ユーザーID
        summary_id (UUID): 親 summary の ID
        segment_id (int): transcript segment の ID

    Returns:
        TranscriptSegment | None: 見つかった場合は transcript segment を返す. 見つからなかった場合は None を返す.
    """
    summary = await get_owned_summary(db_session, user_id, summary_id)
    if summary is None:
        return None
    segment = await db_session.get(TranscriptSegment, segment_id)
    if segment is None or segment.summary_id != summary.id:
        return None
    return segment


async def _rank_after(db_session: AsyncSession, summary_id: UUID, anchor_rank: str | None) -> str | None:
    """Summary 内で anchor_rank の直後(次に大きい rank)を返す.

    Args:
        db_session (AsyncSession): データベースセッション
        summary_id (UUID): 親 summary の ID
        anchor_rank (str | None): 基準 rank. None なら先頭 (最小 rank) を返す.

    Returns:
        str | None: anchor_rank の直後の rank. 見つからなかった場合は None を返す.
    """
    stmt = select(TranscriptSegment.rank).where(col(TranscriptSegment.summary_id) == summary_id)
    if anchor_rank is not None:
        stmt = stmt.where(col(TranscriptSegment.rank) > anchor_rank)
    stmt = stmt.order_by(col(TranscriptSegment.rank)).limit(1)
    return (await db_session.exec(stmt)).first()


async def insert_segment(
    db_session: AsyncSession,
    summary_id: UUID,
    body: TranscriptSegmentCreate,
    anchor: TranscriptSegment | None,
) -> TranscriptSegment:
    """Anchor の直後(anchor=Noneなら先頭)に新しい transcript segment を挿入する.

    Args:
        db_session (AsyncSession): データベースセッション
        summary_id (UUID): 親 summary の ID
        body (TranscriptSegmentCreate): 新しい transcript segment のデータ
        anchor (TranscriptSegment | None): 挿入位置の基準となる segment. None なら先頭に挿入する.

    Returns:
        TranscriptSegment: 挿入された transcript segment

    Raises:
        ValueError: end_ms が start_ms 以下の場合に送出される
    """
    if body.end_ms <= body.start_ms:
        msg = "end_ms は start_ms より大きくなければなりません"
        raise ValueError(msg)

    lo = anchor.rank if anchor else None
    hi = await _rank_after(db_session, summary_id, lo)

    segment = TranscriptSegment(
        summary_id=summary_id,
        rank=generate_key_between(lo, hi),
        speaker_label=body.speaker_label,
        start_ms=body.start_ms,
        end_ms=body.end_ms,
        text=body.text
    )
    db_session.add(segment)
    await db_session.commit()
    return segment


async def update_segment(
    db_session: AsyncSession,
    segment: TranscriptSegment,
    edit: TranscriptSegmentEdit,
) -> TranscriptSegment:
    """送られたフィールドだけ transcript segment を部分更新する.

    Args:
        db_session (AsyncSession): データベースセッション
        segment (TranscriptSegment): 更新対象の transcript segment
        edit (TranscriptSegmentEdit): 更新内容

    Returns:
        TranscriptSegment: 更新後の transcript segment

    Raises:
        ValueError: end_ms が start_ms 以下の場合に送出される
    """
    for field, value in edit.model_dump(exclude_unset=True).items():
        if value is None:
            msg = f"{field} は None にできません"
            raise ValueError(msg)
        setattr(segment, field, value)
    if segment.end_ms <= segment.start_ms:
        msg = "end_ms は start_ms より大きくなければなりません"
        raise ValueError(msg)
    db_session.add(segment)
    await db_session.commit()
    return segment


async def delete_segment(db_session: AsyncSession, segment: TranscriptSegment) -> None:
    """Transcript segment を1件削除する. rank に gap ができても残りの相対順序は不変."""
    await db_session.delete(segment)
    await db_session.commit()


async def split_segment(
    db_session: AsyncSession,
    segment: TranscriptSegment,
    body: TranscriptSegmentSplit,
) -> list[TranscriptSegment]:
    """セグメントの at_ms の位置で2つに分割する.

    Args:
        db_session (AsyncSession): データベースセッション
        segment (TranscriptSegment): 分割対象の transcript segment
        body (TranscriptSegmentSplit): 分割位置と分割後のテキスト

    Returns:
        list[TranscriptSegment]: 分割後の2つの transcript segment

    Raises:
        ValueError: at_ms が segment の start_ms より小さいか end_ms より大きい場合に送出される
    """
    if not segment.start_ms < body.at_ms < segment.end_ms:
        msg = "at_ms は segment の start_ms より大きく、end_ms より小さくなければなりません"
        raise ValueError(msg)

    next_rank = await _rank_after(db_session, segment.summary_id, segment.rank)
    second = TranscriptSegment(
        summary_id=segment.summary_id,
        rank=generate_key_between(segment.rank, next_rank),
        speaker_label=body.speaker_after if body.speaker_after is not None else segment.speaker_label,
        start_ms=body.at_ms,
        end_ms=segment.end_ms,
        text=body.text_after
    )

    segment.end_ms = body.at_ms
    segment.text = body.text_before
    segment.speaker_label = body.speaker_before if body.speaker_before is not None else segment.speaker_label
    db_session.add(segment)
    db_session.add(second)
    await db_session.commit()
    return [segment, second]


async def merge_segments(
    db_session: AsyncSession,
    summary_id: UUID,
    segment_ids: list[int],
    speaker_label: str | None = None
) -> TranscriptSegment | None:
    """指定した複数セグメントを一つに結合する. どれかが summary に属さない場合は None を返す.

    Args:
        db_session (AsyncSession): データベースセッション
        summary_id (UUID): 親 summary の ID
        segment_ids (list[int]): 結合する transcript segment の ID のリスト
        speaker_label (str | None): 結合後のセグメントの話者ラベル. None の場合は最初のセグメントの話者ラベルを使用する.

    Returns:
        TranscriptSegment | None: 結合後の transcript segment. どれかが summary に属さない場合は None を返す.
    """
    stmt = (
        select(TranscriptSegment)
        .where(
            col(TranscriptSegment.summary_id) == summary_id,
            col(TranscriptSegment.id).in_(segment_ids)
        )
        .order_by(col(TranscriptSegment.rank))
    )
    segments = list((await db_session.exec(stmt)).all())
    if len(segments) != len(set(segment_ids)):
        return None  # どれかが summary に属さない場合は None を返す

    survivor = segments[0]  # 最初のセグメントを残す. rank はそのままにする
    if speaker_label is not None:
        survivor.speaker_label = speaker_label
    survivor.text = " ".join(s.text for s in segments)
    survivor.start_ms = min(s.start_ms for s in segments)
    survivor.end_ms = max(s.end_ms for s in segments)
    db_session.add(survivor)
    for seg in segments[1:]:
        await db_session.delete(seg)
    await db_session.commit()
    return survivor


async def rename_speaker(
    db_session: AsyncSession,
    summary_id: UUID,
    old_label: str,
    new_label: str
) -> int:
    """Summary 内の話者ラベルを一括で old_label -> new_label に変更し, 更新行数を返す.

    Args:
        db_session (AsyncSession): データベースセッション
        summary_id (UUID): 親 summary の ID
        old_label (str): 変更前の話者ラベル
        new_label (str): 変更後の話者ラベル

    Returns:
        int: 更新された行数
    """
    stmt = (
        update(TranscriptSegment)
        .where(
            col(TranscriptSegment.summary_id) == summary_id,
            col(TranscriptSegment.speaker_label) == old_label
        )
        .values(speaker_label=new_label)
    )
    result = await db_session.exec(stmt)
    await db_session.commit()
    return result.rowcount
