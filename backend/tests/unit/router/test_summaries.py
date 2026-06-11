from __future__ import annotations

from http import HTTPStatus
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.db.engine import get_session
from app.db.models import Summary as DBSummary
from main import app

if TYPE_CHECKING:
    from collections.abc import Generator

client = TestClient(app)

_PAGE_AND_COUNT_QUERIES = 2


@pytest.fixture(autouse=True)
def clear_session_override() -> Generator[None]:
    """テスト後に dependency_overrides をクリアする pytest フィクスチャ.

    Yields:
        None: テスト本体に制御を返すためのジェネレーター.
    """
    yield
    app.dependency_overrides.clear()  # テスト終了後に dependency_overrides をクリアして、テスト間の副作用を防止


def _install_session(session: AsyncMock) -> None:
    """指定したセッションモックを get_session の override として登録する関数.

    Args:
        session (AsyncMock): エンドポイントに注入するセッションのモック.
    """

    def override_get_session() -> Generator[AsyncMock]:
        """get_session のモックで、テスト用のセッションを提供するジェネレーター関数.

        Yields:
            AsyncMock: テスト用のセッションのモック.
        """
        yield session

    # get_session を override_get_session に置き換えて、
    # テスト中はエンドポイントがテスト用のセッションモックを受け取るようにする
    app.dependency_overrides[get_session] = override_get_session


def test_get_summary_returns_404_when_missing() -> None:
    """存在しない summary_id への GET が 404 を返すことを確認するテスト."""
    session = AsyncMock()
    session.get.return_value = None
    _install_session(session)

    response = client.get(f"/summaries/{uuid4()}")

    assert response.status_code == HTTPStatus.NOT_FOUND


def test_get_summary_returns_detail_with_children() -> None:
    """存在する summary の GET が子要素込みの詳細を返すことを確認するテスト."""
    summary = DBSummary(filename="meeting.mp3", content_hash="abc", overall_summary="overall")
    session = AsyncMock()
    session.get.return_value = summary
    result = MagicMock()
    result.all.return_value = []
    session.exec.return_value = result
    _install_session(session)

    response = client.get(f"/summaries/{summary.id}")

    assert response.status_code == HTTPStatus.OK
    body = response.json()
    assert body["filename"] == "meeting.mp3"
    assert body["overall_summary"] == "overall"
    assert body["topics"] == []
    assert body["decisions"] == []
    assert body["action_items"] == []


def test_list_summaries_uses_window_total_for_nonempty_page() -> None:
    """ページに行があるとき window 関数の total が使われ、追加の COUNT が走らないことを確認するテスト."""
    total = 5
    rows = [
        (DBSummary(filename="a.mp3", overall_summary="o1"), total),
        (DBSummary(filename="b.mp3", overall_summary="o2"), total),
    ]
    result = MagicMock()
    result.all.return_value = rows
    session = AsyncMock()
    session.exec.return_value = result
    _install_session(session)

    response = client.get("/summaries", params={"limit": 2, "offset": 0})

    assert response.status_code == HTTPStatus.OK
    body = response.json()
    assert body["total"] == total
    assert [item["filename"] for item in body["items"]] == ["a.mp3", "b.mp3"]
    session.exec.assert_awaited_once()


def test_list_summaries_empty_page_falls_back_to_count_query() -> None:
    """ページが空のとき別 COUNT クエリの結果が total になることを確認するテスト."""
    total = 7
    page_result = MagicMock()
    page_result.all.return_value = []
    count_result = MagicMock()
    count_result.one.return_value = total
    session = AsyncMock()
    session.exec.side_effect = [page_result, count_result]
    _install_session(session)

    response = client.get("/summaries", params={"limit": 50, "offset": 100})

    assert response.status_code == HTTPStatus.OK
    body = response.json()
    assert body["items"] == []
    assert body["total"] == total
    assert session.exec.await_count == _PAGE_AND_COUNT_QUERIES
