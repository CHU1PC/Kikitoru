from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.db import engine as engine_module

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession


def test_get_session_yields_session_and_closes() -> None:
    """正常終了時はセッションが提供され、rollback されずに close されることを確認するテスト."""
    db_session = AsyncMock()

    async def consume() -> AsyncSession:
        """get_db_session を正常系で最後まで消費する関数.

        Returns:
            AsyncSession: get_db_session が yield したセッション.
        """
        gen = engine_module.get_db_session()
        yielded = await anext(gen)
        await anext(gen, None)
        return yielded

    with patch.object(engine_module, "async_session", MagicMock(return_value=db_session)):
        yielded = asyncio.run(consume())

    assert yielded is db_session
    db_session.rollback.assert_not_awaited()
    db_session.close.assert_awaited_once()


@pytest.mark.parametrize("exc_type", [RuntimeError, asyncio.CancelledError])
def test_get_session_rolls_back_and_reraises_on_exception(exc_type: type[BaseException]) -> None:
    """セッションの yield 中の例外で rollback してから同じ例外を再送出し、close されることを確認するテスト.

    Args:
        exc_type (type[BaseException]): yield 地点に注入する例外の型. CancelledError は
            Exception を継承しないため、except BaseException でないと rollback されない.
    """
    db_session = AsyncMock()

    async def consume_with_error() -> None:
        """get_db_session の yield 中に例外を送出する関数."""
        gen = engine_module.get_db_session()
        await anext(gen)
        await gen.athrow(exc_type("boom"))

    with (
        patch.object(engine_module, "async_session", MagicMock(return_value=db_session)),
        pytest.raises(exc_type, match="boom"),
    ):
        asyncio.run(consume_with_error())

    db_session.rollback.assert_awaited_once()
    db_session.close.assert_awaited_once()
