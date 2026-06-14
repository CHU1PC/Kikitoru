from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession

from app.settings.config import settings

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


engine = create_async_engine(
    settings.DATABASE_URL.get_secret_value(),
    echo=False,
    pool_pre_ping=True,
    connect_args={"ssl": settings.DATABASE_SSL_MODE},
)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db_session() -> AsyncGenerator[AsyncSession]:
    """FastAPI の依存性として使うデータベースセッションを提供する関数.

    例外発生時は明示的に rollback してから再送出し、部分的に適用された変更が
    接続プールに戻る前に破棄されるようにする.

    Yields:
        AsyncSession: リクエスト処理中に使用するデータベースセッション.
    """
    db_session = async_session()
    try:
        yield db_session
    except BaseException:
        await db_session.rollback()
        raise
    finally:
        # ruff ASYNC119 を避けるため try/finally で書いている.
        # しかし`async with` 版が SQLAlchemy の __aexit__ で
        # 持っていたキャンセル耐性を失ってしまうため close は shield で保護する.
        # クライアント切断等でタスクがキャンセルされても close を完走させ、接続を確実にプールへ返す.
        await asyncio.shield(db_session.close())


DbSessionDep = Annotated[AsyncSession, Depends(get_db_session)]
