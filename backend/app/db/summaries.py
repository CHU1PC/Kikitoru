from __future__ import annotations

from typing import TYPE_CHECKING

from fractional_indexing import generate_n_keys_between
from sqlalchemy import ColumnElement, func
from sqlalchemy.exc import IntegrityError
from sqlmodel import col, select

from app.db.models import ActionItem, Decision, Summary, Topic, TranscriptSegment
from app.schema.summaries import ActionItemResponse, DecisionResponse, SummaryResponse, TopicResponse

if TYPE_CHECKING:
    from uuid import UUID

    from sqlmodel.ext.asyncio.session import AsyncSession

    from app.llm.summarize.schema import Summary as LLMSummary
    from app.stt.types import Segment


async def build_summary_read(db_session: AsyncSession, summary: Summary) -> SummaryResponse:
    """要約の子要素を安定した id 順で読み込み、read モデルを組み立てる.

    詳細エンドポイントと audio ルータの冪等ヒットの両方で共有され、DB から
    同一かつ決定的な順序のペイロードを返す.

    Args:
        db_session (AsyncSession): SQLAlchemy の非同期セッション.
        summary (Summary): 既に読み込まれた親の要約行.

    Returns:
        SummaryResponse: トピック・決定事項・アクションアイテムを含む要約.
    """
    topics = (
        await db_session.exec(
            select(Topic).where(col(Topic.summary_id) == summary.id).order_by(col(Topic.id))
        )
    ).all()
    decisions = (
        await db_session.exec(
            select(Decision).where(col(Decision.summary_id) == summary.id).order_by(col(Decision.id))
        )
    ).all()
    action_items = (
        await db_session.exec(
            select(ActionItem).where(col(ActionItem.summary_id) == summary.id).order_by(col(ActionItem.id))
        )
    ).all()

    return SummaryResponse(
        id=summary.id,
        filename=summary.filename,
        created_at=summary.created_at,
        overall_summary=summary.overall_summary,
        group_id=summary.group_id,
        topics=[TopicResponse.model_validate(t) for t in topics],
        decisions=[DecisionResponse.model_validate(d) for d in decisions],
        action_items=[ActionItemResponse.model_validate(a) for a in action_items],
    )


async def get_owned_summary(
    db_session: AsyncSession,
    user_id: UUID,
    summary_id: UUID,
    *,
    include_deleted: bool = False,
) -> Summary | None:
    """Owner & (任意で) soft-delete を考慮して取得.

    Args:
        db_session (AsyncSession): SQLAlchemy の非同期セッション.
        user_id (UUID): 検索対象の所有者.
        summary_id (UUID): 検索対象の要約の id.
        include_deleted (bool, optional): True の場合、削除済みの要約も返す. Defaults to False.

    Returns:
        Summary | None: 一致する要約行. 未保存なら None.
    """
    stmt = select(Summary).where(
        col(Summary.id) == summary_id,
        col(Summary.user_id) == user_id,
    )
    if not include_deleted:
        stmt = stmt.where(col(Summary.deleted_at).is_(None))
    return (await db_session.exec(stmt)).first()


async def find_by_content_hash(db_session: AsyncSession, user_id: UUID, content_hash: str) -> Summary | None:
    """このユーザーの音声内容に対して既に保存されている要約を返す. 無ければ None.

    Args:
        db_session (AsyncSession): SQLAlchemy の非同期セッション.
        user_id (UUID): 検索対象の所有者.
        content_hash (str): アップロード音声の SHA-256 hex ダイジェスト.

    Returns:
        Summary | None: 一致する要約行. 未保存なら None.
    """
    return (
        await db_session.exec(
            select(Summary).where(
                col(Summary.user_id) == user_id,
                col(Summary.content_hash) == content_hash,
            )
        )
    ).first()


async def list_summaries_page(
    db_session: AsyncSession,
    user_id: UUID,
    *,
    deleted: bool,
    limit: int,
    offset: int,
    group_id: UUID | None = None,
    ungrouped_only: bool = False,
) -> tuple[list[Summary], int]:
    """User の要約を作成日時の降順でページ取得する.

    アクティブ一覧 (deleted=False) とゴミ箱一覧 (deleted=True) で共有し、
    deleted_at フィルタの向きだけ切り替える (重複クエリと count フィルタの取り違えを防ぐ).

    Args:
        db_session (AsyncSession): SQLAlchemy の非同期セッション.
        user_id (UUID): 検索対象の所有者.
        deleted (bool): True なら削除済み (ゴミ箱), False ならアクティブな要約を返す.
        limit (int): 1ページあたりの最大件数.
        offset (int): スキップする件数.
        group_id (UUID | None): 検索対象の要約グループの ID.
        ungrouped_only (bool): True なら未分類の要約のみを返す.

    Returns:
        tuple[list[Summary], int]: ページ内の要約行と、フィルタ条件に一致する総件数.
    """
    filters: list[ColumnElement[bool]] = [
        col(Summary.user_id) == user_id,
        col(Summary.deleted_at).is_not(None) if deleted else col(Summary.deleted_at).is_(None),
    ]
    if ungrouped_only:
        filters.append(col(Summary.group_id).is_(None))
    elif group_id is not None:
        filters.append(col(Summary.group_id) == group_id)
    total_col = func.count().over()
    rows = (
        await db_session.exec(
            select(Summary, total_col)
            .where(*filters)
            .order_by(col(Summary.created_at).desc(), col(Summary.id).desc())
            .limit(limit)
            .offset(offset)
        )
    ).all()
    if rows:
        return [summary for summary, _ in rows], int(rows[0][1])
    total = (
        await db_session.exec(
            select(func.count())
            .select_from(Summary)
            .where(*filters)
        )
    ).one()
    return [], total


def _add_all_children(db_session: AsyncSession, summary_id: UUID, data: LLMSummary) -> None:
    """要約のトピック・決定事項・アクションアイテムを insert 用に登録する.

    Args:
        db_session (AsyncSession): SQLAlchemy の非同期セッション.
        summary_id (UUID): 親要約の id (flush 後に確定).
        data (LLMSummary): LLM が生成した構造化要約.
    """
    for t in data.topics:
        db_session.add(Topic(summary_id=summary_id, title=t.title, summary=t.summary))
    for d in data.decisions:
        db_session.add(Decision(summary_id=summary_id, description=d.description, decided_by=d.decided_by))
    for action_item in data.action_items:
        db_session.add(
            ActionItem(
                summary_id=summary_id,
                description=action_item.description,
                assignee=action_item.assignee,
                due_date=action_item.due_date,
            )
        )


def _add_segments(
    db_session: AsyncSession,
    summary_id: UUID,
    segments: list[Segment],
) -> None:
    """STT の Segment(ms 整数) を TranscriptSegment として insert 用に登録する.

    rank は時系列((start_ms, end_ms))順に fractional index を一括採番する. これにより
    read は rank 順に取得でき、後続の編集(挿入/分割)は隣接 rank の間へ差せる.

    Args:
        db_session (AsyncSession): SQLAlchemy の非同期セッション.
        summary_id (UUID): 親要約の id (flush 後に確定).
        segments (list[Segment]): STT の話者分離済み文字起こしセグメント.
    """
    ordered = sorted(segments, key=lambda seg: (seg.start_ms, seg.end_ms))
    ranks = generate_n_keys_between(None, None, len(ordered))
    for seg, rank in zip(ordered, ranks, strict=True):
        db_session.add(
            TranscriptSegment(
                summary_id=summary_id,
                rank=rank,
                speaker_label=seg.speaker_label,
                start_ms=seg.start_ms,
                end_ms=seg.end_ms,
                text=seg.text,
            )
        )


async def create_summary(
    db_session: AsyncSession,
    user_id: UUID,
    filename: str,
    content_hash: str,
    data: LLMSummary,
    segments: list[Segment],
) -> SummaryResponse:
    """要約と、それに紐づくトピック・決定事項・アクションアイテムを永続化する.

    Args:
        db_session (AsyncSession): SQLAlchemy の非同期セッション.
        user_id (UUID): 要約の所有者.
        filename (str): アップロードされた音声ファイル名.
        content_hash (str): アップロード音声の SHA-256 hex ダイジェスト.
        data (LLMSummary): LLM が生成した構造化要約.
        segments (list[Segment]): STT の話者分離済み文字起こしセグメント.

    Returns:
        SummaryResponse: 作成された (または content_hash 競合時は既存の) 要約.

    Raises:
        IntegrityError: (user_id, content_hash) の重複以外の理由で commit が失敗した場合
            (重複競合は既存行を返すことで処理される).
    """
    summary = Summary(
        user_id=user_id, filename=filename, content_hash=content_hash, overall_summary=data.overall_summary
    )
    try:
        db_session.add(summary)
        await db_session.flush()
        _add_all_children(db_session, summary.id, data)
        _add_segments(db_session, summary.id, segments)
        await db_session.commit()
    except IntegrityError:
        await db_session.rollback()
        existing = await find_by_content_hash(db_session, user_id, content_hash)
        if existing is not None:
            return await build_summary_read(db_session, existing)
        raise

    return await build_summary_read(db_session, summary)


async def get_transcript_segments(db_session: AsyncSession, summary_id: UUID) -> list[TranscriptSegment]:
    """Summary の transcript セグメントを rank 順(rank, id)で返す.

    rank 列は COLLATE "C" (byte 順) なので、素の ORDER BY rank が
    Python の辞書順・fractional-indexing の意図順と一致する.

    Args:
        db_session (AsyncSession): SQLAlchemy の非同期セッション.
        summary_id (UUID): 要約の id.

    Returns:
        list[TranscriptSegment]: 該当する文字起こしセグメントのリスト.
    """
    return list((
        await db_session.exec(
            select(TranscriptSegment)
            .where(col(TranscriptSegment.summary_id) == summary_id)
            .order_by(
                col(TranscriptSegment.rank),
                col(TranscriptSegment.id)
            )
        )).all()
    )
