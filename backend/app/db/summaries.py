from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlmodel import col, select

from app.db.models import ActionItem, Decision, Summary, Topic
from app.schema.summaries import ActionItemResponse, DecisionResponse, SummaryResponse, TopicResponse

if TYPE_CHECKING:
    from uuid import UUID

    from sqlmodel.ext.asyncio.session import AsyncSession

    from app.llm.summarize.schema import Summary as LLMSummary


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

    Returns:
        tuple[list[Summary], int]: ページ内の要約行と、フィルタ条件に一致する総件数.
    """
    deleted_filter = col(Summary.deleted_at).is_not(None) if deleted else col(Summary.deleted_at).is_(None)
    total_col = func.count().over().label("total")
    rows = (
        await db_session.exec(
            select(Summary, total_col)
            .where(col(Summary.user_id) == user_id, deleted_filter)
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
            .where(
                col(Summary.user_id) == user_id, deleted_filter
            )
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


async def create_summary(
    db_session: AsyncSession, user_id: UUID, filename: str, content_hash: str, data: LLMSummary
) -> SummaryResponse:
    """要約と、それに紐づくトピック・決定事項・アクションアイテムを永続化する.

    Args:
        db_session (AsyncSession): SQLAlchemy の非同期セッション.
        user_id (UUID): 要約の所有者.
        filename (str): アップロードされた音声ファイル名.
        content_hash (str): アップロード音声の SHA-256 hex ダイジェスト.
        data (LLMSummary): LLM が生成した構造化要約.

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
        await db_session.commit()
    except IntegrityError:
        await db_session.rollback()
        existing = await find_by_content_hash(db_session, user_id, content_hash)
        if existing is not None:
            return await build_summary_read(db_session, existing)
        raise

    return await build_summary_read(db_session, summary)
