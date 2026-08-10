from __future__ import annotations

from typing import TYPE_CHECKING

from sqlmodel import select

from app.db.models import SummaryGroup
from app.dependencies import col

if TYPE_CHECKING:
    from uuid import UUID

    from sqlmodel.ext.asyncio.session import AsyncSession


async def get_owned_group(db_session: AsyncSession, user_id: UUID, group_id: UUID) -> SummaryGroup | None:
    """Owner を考慮して取得.

    Args:
        db_session (AsyncSession): SQLAlchemy の非同期セッション.
        user_id (UUID): 検索対象の所有者.
        group_id (UUID): 検索対象の要約グループの id.

    Returns:
        SummaryGroup | None: 一致する要約グループ行. 未保存なら None.
    """
    stmt = select(SummaryGroup).where(
        col(SummaryGroup.id) == group_id,
        col(SummaryGroup.user_id) == user_id,
    )
    return (await db_session.exec(stmt)).first()


async def list_groups(db_session: AsyncSession, user_id: UUID) -> list[SummaryGroup]:
    """Owner を考慮して一覧取得.

    Args:
        db_session (AsyncSession): SQLAlchemy の非同期セッション.
        user_id (UUID): 検索対象の所有者.

    Returns:
        list[SummaryGroup]: 一致する要約グループ行のリスト.
    """
    stmt = select(SummaryGroup).where(col(SummaryGroup.user_id) == user_id).order_by(col(SummaryGroup.name))
    return list((await db_session.exec(stmt)).all())


async def create_group(db_session: AsyncSession, group: SummaryGroup) -> SummaryGroup:
    """グループを一つ作成して返す.

    Args:
        db_session (AsyncSession): SQLAlchemy の非同期セッション.
        group (SummaryGroup): 作成する要約グループの行.

    Returns:
        SummaryGroup: 作成された要約グループの行.
    """
    db_session.add(group)
    await db_session.commit()
    return group


async def rename_group(db_session: AsyncSession, group: SummaryGroup, name: str) -> SummaryGroup:
    """グループの名前を変更して返す.

    Args:
        db_session (AsyncSession): SQLAlchemy の非同期セッション.
        group (SummaryGroup): 変更対象の要約グループの行.
        name (str): 新しい名前.

    Returns:
        SummaryGroup: 変更後の要約グループの行.
    """
    group.name = name
    db_session.add(group)
    await db_session.commit()
    return group


async def delete_group(db_session: AsyncSession, group: SummaryGroup) -> None:
    """フォルダを削除する. 中の要約は FK の SET NULL で未分類に戻る.

    Args:
        db_session (AsyncSession): SQLAlchemy の非同期セッション.
        group (SummaryGroup): 既に読み込まれたフォルダ.
    """
    await db_session.delete(group)
    await db_session.commit()
