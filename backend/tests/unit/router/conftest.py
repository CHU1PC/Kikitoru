from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from app.rate_limit import limiter
from main import app

if TYPE_CHECKING:
    from collections.abc import Generator


@pytest.fixture(autouse=True)
def clear_dependency_overrides() -> Generator[None]:
    """各テスト後に dependency_overrides をクリアし、テスト間の汚染を防ぐ pytest フィクスチャ.

    Yields:
        None: テスト本体に制御を返すためのジェネレーター.
    """
    yield
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def reset_rate_limiter() -> None:
    """各テスト前にレート制限のカウンタを reset し、テスト間でカウントが漏れるのを防ぐ pytest フィクスチャ."""
    limiter.reset()
