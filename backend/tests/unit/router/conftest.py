from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from main import app

if TYPE_CHECKING:
    from collections.abc import Generator


@pytest.fixture(autouse=True)  # noqa: RUF076 - 全テストに一律で後始末を効かせる必要があるため autouse が適切
def clear_dependency_overrides() -> Generator[None]:
    """各テスト後に dependency_overrides をクリアし、テスト間の汚染を防ぐ pytest フィクスチャ.

    Yields:
        None: テスト本体に制御を返すためのジェネレーター.
    """
    yield
    app.dependency_overrides.clear()
