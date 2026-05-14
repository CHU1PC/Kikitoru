from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession

from app.settings.config import settings

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


engine = create_async_engine(settings.DATABASE_URL, echo=False, pool_pre_ping=True)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_session() -> AsyncGenerator[AsyncSession]:
    """Yield a database session for use as a FastAPI dependency."""
    async with async_session() as session:
        yield session
