from __future__ import annotations

from typing import TYPE_CHECKING

from app.db.models import ActionItem, Decision, Topic
from app.db.summaries import get_owned_summary

if TYPE_CHECKING:
    from uuid import UUID

    from sqlmodel.ext.asyncio.session import AsyncSession

    from app.schema.summaries import ActionItemEdit, DecisionEdit, TopicEdit

# 子テーブルの NOT NULL フィールド ( Edit で null を拒否する対象)
_REQUIRED_CHILD_FIELDS: dict[type, set[str]] = {
    Topic: {"title", "summary"},
    Decision: {"description"},
    ActionItem: {"description"},
}


async def load_owned_child[ChildT: (Topic, Decision, ActionItem)](
    db_session: AsyncSession,
    user_id: UUID,
    summary_id: UUID,
    child_model: type[ChildT],
    child_id: int,
) -> ChildT | None:
    """親 summary の所有を確認した上で、子要素を取得する. 存在しない場合は None を返す.

    子 PK は autoincrement で推測可能なため、まず親 summary の所有を検証し、
    その子が本当にその summary に属するか (child.summary_id == summary.id) も確認する.

    Args:
        db_session (AsyncSession): SQLAlchemy の非同期セッション.
        user_id (UUID): 親 summary の所有者.
        summary_id (UUID): 親 summary の id.
        child_model (ChildT): 子要素のモデルクラス (Topic, Decision, ActionItem のいずれか).
        child_id (int): 子要素の id.

    Returns:
        ChildT | None: 存在する場合は子要素の行. 存在しない場合は None.
    """
    summary = await get_owned_summary(db_session, user_id, summary_id)
    if summary is None:
        return None
    child = await db_session.get(child_model, child_id)
    if child is None or child.summary_id != summary.id:
        return None
    return child


async def add_child[ChildT: (Topic, Decision, ActionItem)](db_session: AsyncSession, child: ChildT) -> ChildT:
    """子要素を1件追加して commit し、採番された id 付きで返す.

    Args:
        db_session (AsyncSession): SQLAlchemy の非同期セッション.
        child (ChildT): 追加する子要素の行.

    Returns:
        ChildT: 追加後の子要素の行 (id が確定している).
    """
    db_session.add(child)
    await db_session.commit()
    return child


async def update_child[ChildT: (Topic, Decision, ActionItem)](
    db_session: AsyncSession, child: ChildT, edit: TopicEdit | DecisionEdit | ActionItemEdit
) -> ChildT:
    """送られたフィールドだけ子要素を部分更新する.

    Args:
        db_session (AsyncSession): SQLAlchemy の非同期セッション.
        child (ChildT): 更新対象の子要素の行.
        edit (TopicEdit | DecisionEdit | ActionItemEdit): 更新内容を持つリクエストボディ.

    Returns:
        ChildT: 更新後の子要素の行.

    Raises:
        ValueError: NOT NULL のフィールドに null を設定しようとした場合 (router で 422 に変換する).
    """
    required = _REQUIRED_CHILD_FIELDS[type(child)]
    for field, value in edit.model_dump(exclude_unset=True).items():
        if value is None and field in required:
            msg = f"{field} は null にできません"
            raise ValueError(msg)
        setattr(child, field, value)
    db_session.add(child)
    await db_session.commit()
    return child


async def delete_child[ChildT: (Topic, Decision, ActionItem)](db_session: AsyncSession, child: ChildT) -> None:
    """子要素を1件削除する."""
    await db_session.delete(child)
    await db_session.commit()
