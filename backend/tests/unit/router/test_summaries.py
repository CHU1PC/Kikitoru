from __future__ import annotations

from http import HTTPStatus
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from fastapi.testclient import TestClient

from app.db.engine import get_db_session
from app.db.models import Summary as DBSummary
from app.db.models import User
from app.dependencies import get_current_user
from main import app

if TYPE_CHECKING:
    from collections.abc import Generator

client = TestClient(app)

_USER = User(id=uuid4(), email="owner@example.com", name="Owner")
_PAGE_AND_COUNT_QUERIES = 2


def _install_session(db_session: AsyncMock) -> None:
    """指定したセッションモックを get_db_session の override として登録する関数.

    Args:
        db_session (AsyncMock): エンドポイントに注入するセッションのモック.
    """

    def override_get_session() -> Generator[AsyncMock]:
        """get_db_session のモックで、テスト用のセッションを提供するジェネレーター関数.

        Yields:
            AsyncMock: テスト用のセッションのモック.
        """
        yield db_session

    # get_db_session を override_get_session に置き換えて、
    # テスト中はエンドポイントがテスト用のセッションモックを受け取るようにする
    app.dependency_overrides[get_db_session] = override_get_session
    app.dependency_overrides[get_current_user] = lambda: _USER


def test_get_summary_returns_404_when_missing() -> None:
    """存在しない summary_id への GET が 404 を返すことを確認するテスト."""
    db_session = AsyncMock()
    db_session.get.return_value = None
    _install_session(db_session)

    response = client.get(f"/api/v1/summaries/{uuid4()}")

    assert response.status_code == HTTPStatus.NOT_FOUND


def test_get_summary_returns_detail_with_children() -> None:
    """存在する自分の summary の GET が子要素込みの詳細を返すことを確認するテスト."""
    summary = DBSummary(user_id=_USER.id, filename="meeting.mp3", content_hash="abc", overall_summary="overall")
    db_session = AsyncMock()
    db_session.get.return_value = summary
    result = MagicMock()
    result.all.return_value = []
    db_session.exec.return_value = result
    _install_session(db_session)

    response = client.get(f"/api/v1/summaries/{summary.id}")

    assert response.status_code == HTTPStatus.OK
    body = response.json()
    assert body["filename"] == "meeting.mp3"
    assert body["overall_summary"] == "overall"
    assert body["topics"] == []
    assert body["decisions"] == []
    assert body["action_items"] == []


def test_get_summary_returns_404_for_other_users_summary() -> None:
    """他人の summary を GET したとき存在を隠して 404 を返すことを確認するテスト."""
    summary = DBSummary(user_id=uuid4(), filename="secret.mp3", content_hash="abc", overall_summary="secret")
    db_session = AsyncMock()
    db_session.get.return_value = summary
    _install_session(db_session)

    response = client.get(f"/api/v1/summaries/{summary.id}")

    assert response.status_code == HTTPStatus.NOT_FOUND


def test_get_summary_requires_authentication() -> None:
    """未認証のとき summary 詳細 GET が 401 を返すことを確認するテスト."""
    _install_session(AsyncMock())
    app.dependency_overrides.pop(get_current_user, None)

    response = client.get(f"/api/v1/summaries/{uuid4()}")

    assert response.status_code == HTTPStatus.UNAUTHORIZED


def test_list_summaries_uses_window_total_for_nonempty_page() -> None:
    """ページに行があるとき window 関数の total が使われ、追加の COUNT が走らないことを確認するテスト."""
    total = 5
    rows = [
        (DBSummary(user_id=uuid4(), filename="a.mp3", overall_summary="o1"), total),
        (DBSummary(user_id=uuid4(), filename="b.mp3", overall_summary="o2"), total),
    ]
    result = MagicMock()
    result.all.return_value = rows
    db_session = AsyncMock()
    db_session.exec.return_value = result
    _install_session(db_session)

    response = client.get("/api/v1/summaries", params={"limit": 2, "offset": 0})

    assert response.status_code == HTTPStatus.OK
    body = response.json()
    assert body["total"] == total
    assert [item["filename"] for item in body["items"]] == ["a.mp3", "b.mp3"]
    db_session.exec.assert_awaited_once()


def test_list_summaries_empty_page_falls_back_to_count_query() -> None:
    """ページが空のとき別 COUNT クエリの結果が total になることを確認するテスト."""
    total = 7
    page_result = MagicMock()
    page_result.all.return_value = []
    count_result = MagicMock()
    count_result.one.return_value = total
    db_session = AsyncMock()
    db_session.exec.side_effect = [page_result, count_result]
    _install_session(db_session)

    response = client.get("/api/v1/summaries", params={"limit": 50, "offset": 100})

    assert response.status_code == HTTPStatus.OK
    body = response.json()
    assert body["items"] == []
    assert body["total"] == total
    assert db_session.exec.await_count == _PAGE_AND_COUNT_QUERIES
