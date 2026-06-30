from __future__ import annotations

from datetime import UTC, datetime
from http import HTTPStatus
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from fastapi.testclient import TestClient

from app.db.engine import get_db_session
from app.db.models import Summary as DBSummary
from app.db.models import Topic, User, UserStatus
from app.dependencies import get_current_user
from main import app

if TYPE_CHECKING:
    from collections.abc import Generator

client = TestClient(app)

_USER = User(id=uuid4(), email="owner@example.com", name="Owner", status=UserStatus.approved)
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
    result = MagicMock()
    result.first.return_value = None
    db_session.exec.return_value = result
    _install_session(db_session)

    response = client.get(f"/api/v1/summaries/{uuid4()}")

    assert response.status_code == HTTPStatus.NOT_FOUND


def test_get_summary_returns_detail_with_children() -> None:
    """存在する自分の summary の GET が子要素込みの詳細を返すことを確認するテスト."""
    summary = DBSummary(user_id=_USER.id, filename="meeting.mp3", content_hash="abc", overall_summary="overall")
    get_result = MagicMock()
    get_result.first.return_value = summary
    empty = MagicMock()
    empty.all.return_value = []
    db_session = AsyncMock()
    db_session.exec.side_effect = [get_result, empty, empty, empty]
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
    """他人の summary を GET したとき owner スコープで除外され 404 を返すことを確認するテスト."""
    db_session = AsyncMock()
    result = MagicMock()
    result.first.return_value = None  # 他人の行は get_owned_summary の WHERE user_id で除外され None になる
    db_session.exec.return_value = result
    _install_session(db_session)

    response = client.get(f"/api/v1/summaries/{uuid4()}")

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


def test_patch_summary_updates_fields() -> None:
    """自分の summary への PATCH が指定フィールドを更新し更新後の本体を返すことを確認するテスト."""
    summary = DBSummary(user_id=_USER.id, filename="m.mp3", content_hash="abc", overall_summary="old")
    get_result = MagicMock()
    get_result.first.return_value = summary
    empty = MagicMock()
    empty.all.return_value = []
    db_session = AsyncMock()
    db_session.add = MagicMock()
    db_session.exec.side_effect = [get_result, empty, empty, empty]
    _install_session(db_session)

    response = client.patch(f"/api/v1/summaries/{summary.id}", json={"overall_summary": "new"})

    assert response.status_code == HTTPStatus.OK
    assert response.json()["overall_summary"] == "new"


def test_patch_summary_returns_404_when_missing() -> None:
    """存在しない summary への PATCH が 404 を返すことを確認するテスト."""
    none_result = MagicMock()
    none_result.first.return_value = None
    db_session = AsyncMock()
    db_session.exec.return_value = none_result
    _install_session(db_session)

    response = client.patch(f"/api/v1/summaries/{uuid4()}", json={"overall_summary": "x"})

    assert response.status_code == HTTPStatus.NOT_FOUND


def test_delete_summary_marks_deleted_at() -> None:
    """DELETE が deleted_at をセットして 204 (ソフト削除) を返すことを確認するテスト."""
    summary = DBSummary(user_id=_USER.id, filename="m.mp3", overall_summary="o")
    result = MagicMock()
    result.first.return_value = summary
    db_session = AsyncMock()
    db_session.add = MagicMock()
    db_session.exec.return_value = result
    _install_session(db_session)

    response = client.delete(f"/api/v1/summaries/{summary.id}")

    assert response.status_code == HTTPStatus.NO_CONTENT
    assert summary.deleted_at is not None


def test_restore_returns_404_when_not_trashed() -> None:
    """ゴミ箱に無い (deleted_at が None) summary の復元が 404 を返すことを確認するテスト."""
    summary = DBSummary(user_id=_USER.id, filename="m.mp3", overall_summary="o")
    result = MagicMock()
    result.first.return_value = summary
    db_session = AsyncMock()
    db_session.exec.return_value = result
    _install_session(db_session)

    response = client.post(f"/api/v1/summaries/{summary.id}/restore")

    assert response.status_code == HTTPStatus.NOT_FOUND


def test_permanent_delete_removes_trashed_summary() -> None:
    """ゴミ箱の summary への完全削除が DB から物理削除し 204 を返すことを確認するテスト."""
    summary = DBSummary(user_id=_USER.id, filename="m.mp3", overall_summary="o")
    summary.deleted_at = datetime.now(UTC)
    result = MagicMock()
    result.first.return_value = summary
    db_session = AsyncMock()
    db_session.exec.return_value = result
    _install_session(db_session)

    response = client.delete(f"/api/v1/summaries/{summary.id}/permanent")

    assert response.status_code == HTTPStatus.NO_CONTENT
    db_session.delete.assert_awaited_once_with(summary)


def test_trash_lists_deleted_summaries() -> None:
    """/trash が削除済み summary のページを返すことを確認するテスト."""
    total = 3
    rows = [(DBSummary(user_id=_USER.id, filename="d.mp3", overall_summary="o"), total)]
    result = MagicMock()
    result.all.return_value = rows
    db_session = AsyncMock()
    db_session.exec.return_value = result
    _install_session(db_session)

    response = client.get("/api/v1/summaries/trash")

    assert response.status_code == HTTPStatus.OK
    assert response.json()["total"] == total


def test_create_topic_returns_201_with_assigned_id() -> None:
    """議題の追加が 201 と採番された id 付きの本体を返すことを確認するテスト."""
    summary = DBSummary(user_id=_USER.id, filename="m.mp3", overall_summary="o")
    get_result = MagicMock()
    get_result.first.return_value = summary

    def assign_id(obj: Topic) -> None:
        obj.id = 1  # commit が採番する autoincrement id をモックで再現する

    db_session = AsyncMock()
    db_session.add = MagicMock(side_effect=assign_id)
    db_session.exec.return_value = get_result
    _install_session(db_session)

    response = client.post(f"/api/v1/summaries/{summary.id}/topics", json={"title": "T", "summary": "S"})

    assert response.status_code == HTTPStatus.CREATED
    body = response.json()
    assert body["id"] == 1
    assert body["title"] == "T"


def test_create_topic_returns_404_when_summary_missing() -> None:
    """存在しない summary への議題追加が 404 を返すことを確認するテスト."""
    none_result = MagicMock()
    none_result.first.return_value = None
    db_session = AsyncMock()
    db_session.exec.return_value = none_result
    _install_session(db_session)

    response = client.post(f"/api/v1/summaries/{uuid4()}/topics", json={"title": "T", "summary": "S"})

    assert response.status_code == HTTPStatus.NOT_FOUND


def test_patch_topic_returns_422_when_required_field_null() -> None:
    """NOT NULL の議題フィールドに null を送ると 422 を返すことを確認するテスト."""
    summary = DBSummary(user_id=_USER.id, filename="m.mp3", overall_summary="o")
    topic = Topic(id=1, summary_id=summary.id, title="old", summary="old")
    get_result = MagicMock()
    get_result.first.return_value = summary
    db_session = AsyncMock()
    db_session.add = MagicMock()
    db_session.exec.return_value = get_result
    db_session.get.return_value = topic
    _install_session(db_session)

    response = client.patch(f"/api/v1/summaries/{summary.id}/topics/1", json={"title": None})

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


def test_patch_topic_returns_404_for_other_summarys_child() -> None:
    """他の summary に属する議題 id を指定した PATCH が 404 を返すことを確認するテスト (IDOR 対策)."""
    summary = DBSummary(user_id=_USER.id, filename="m.mp3", overall_summary="o")
    other_topic = Topic(id=1, summary_id=uuid4(), title="x", summary="y")
    get_result = MagicMock()
    get_result.first.return_value = summary
    db_session = AsyncMock()
    db_session.exec.return_value = get_result
    db_session.get.return_value = other_topic
    _install_session(db_session)

    response = client.patch(f"/api/v1/summaries/{summary.id}/topics/1", json={"title": "new"})

    assert response.status_code == HTTPStatus.NOT_FOUND


def test_delete_topic_returns_204() -> None:
    """自分の summary の議題削除が 204 を返し DB から削除されることを確認するテスト."""
    summary = DBSummary(user_id=_USER.id, filename="m.mp3", overall_summary="o")
    topic = Topic(id=1, summary_id=summary.id, title="t", summary="s")
    get_result = MagicMock()
    get_result.first.return_value = summary
    db_session = AsyncMock()
    db_session.exec.return_value = get_result
    db_session.get.return_value = topic
    _install_session(db_session)

    response = client.delete(f"/api/v1/summaries/{summary.id}/topics/1")

    assert response.status_code == HTTPStatus.NO_CONTENT
    db_session.delete.assert_awaited_once_with(topic)
