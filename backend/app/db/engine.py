from __future__ import annotations

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


async def get_session() -> AsyncGenerator[AsyncSession]:
    """FastAPI の依存性として使うデータベースセッションを提供する関数.

    例外発生時は明示的に rollback してから再送出し、部分的に適用された変更が
    接続プールに戻る前に破棄されるようにする. async generator 内の `async with` は
    消費側が generator を閉じない場合に cleanup が保証されないため、
    セッションのクローズも try/finally で明示的に行う.

    Yields:
        AsyncSession: リクエスト処理中に使用するデータベースセッション.
    """
    session = async_session()
    try:
        yield session
    except BaseException:
        await session.rollback()
        raise
    finally:
        await session.close()


SessionDep = Annotated[AsyncSession, Depends(get_session)]
