from __future__ import annotations

from typing import TYPE_CHECKING

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
    """Yield a database session for use as a FastAPI dependency.

    Explicitly rolls back on exceptions so that any partially-applied work
    is discarded before the connection returns to the pool. The default
    `async with` behavior is driver-dependent; making the rollback explicit
    keeps the connection state predictable across versions.
    """
    async with async_session() as session:
        try:
            yield session
        except BaseException:
            await session.rollback()
            raise
