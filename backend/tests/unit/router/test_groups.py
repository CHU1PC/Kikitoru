from __future__ import annotations

from http import HTTPStatus
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.db.engine import get_db_session
from app.db.models import SummaryGroup, User, UserStatus
from app.dependencies import get_current_user
from main import app

if TYPE_CHECKING:
    from collections.abc import Generator

client = TestClient(app)

_USER = User(id=uuid4(), email="owner@example.com", name="Owner", status=UserStatus.approved)


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

    app.dependency_overrides[get_db_session] = override_get_session
    app.dependency_overrides[get_current_user] = lambda: _USER


def test_create_group_returns_201() -> None:
    """グループ作成が 201 と作成したグループ本体を返すことを確認するテスト."""
    db_session = AsyncMock()
    db_session.add = MagicMock()
    _install_session(db_session)

    response = client.post("/api/v1/groups", json={"name": "営業系"})

    assert response.status_code == HTTPStatus.CREATED
    body = response.json()
    assert body["name"] == "営業系"
    assert body["id"]


def test_create_group_duplicate_name_returns_400() -> None:
    """同名グループ作成で commit が IntegrityError になったとき rollback して 400 を返すことを確認するテスト."""
    db_session = AsyncMock()
    db_session.add = MagicMock()
    db_session.commit = AsyncMock(side_effect=IntegrityError("stmt", None, Exception("duplicate")))
    _install_session(db_session)

    response = client.post("/api/v1/groups", json={"name": "営業系"})

    assert response.status_code == HTTPStatus.BAD_REQUEST
    db_session.rollback.assert_awaited_once()


def test_list_groups_returns_groups() -> None:
    """グループ一覧 GET が自分のグループ一覧を返すことを確認するテスト."""
    groups = [
        SummaryGroup(user_id=_USER.id, name="営業系"),
        SummaryGroup(user_id=_USER.id, name="開発系"),
    ]
    result = MagicMock()
    result.all.return_value = groups
    db_session = AsyncMock()
    db_session.exec.return_value = result
    _install_session(db_session)

    response = client.get("/api/v1/groups")

    assert response.status_code == HTTPStatus.OK
    assert [g["name"] for g in response.json()] == ["営業系", "開発系"]


def test_rename_group_returns_200() -> None:
    """自分のグループへの PATCH が名前を変更し更新後の本体を返すことを確認するテスト."""
    group = SummaryGroup(user_id=_USER.id, name="営業系")
    result = MagicMock()
    result.first.return_value = group
    db_session = AsyncMock()
    db_session.add = MagicMock()
    db_session.exec.return_value = result
    _install_session(db_session)

    response = client.patch(f"/api/v1/groups/{group.id}", json={"name": "営業チーム"})

    assert response.status_code == HTTPStatus.OK
    assert response.json()["name"] == "営業チーム"


def test_rename_group_returns_404_when_missing() -> None:
    """存在しない (または他人の) グループへの PATCH が owner スコープで除外され 404 を返すことを確認するテスト."""
    result = MagicMock()
    result.first.return_value = None
    db_session = AsyncMock()
    db_session.exec.return_value = result
    _install_session(db_session)

    response = client.patch(f"/api/v1/groups/{uuid4()}", json={"name": "x"})

    assert response.status_code == HTTPStatus.NOT_FOUND


def test_rename_group_duplicate_name_returns_400() -> None:
    """改名先が既存名と衝突して commit が IntegrityError になったとき 400 を返すことを確認するテスト."""
    group = SummaryGroup(user_id=_USER.id, name="営業系")
    result = MagicMock()
    result.first.return_value = group
    db_session = AsyncMock()
    db_session.add = MagicMock()
    db_session.exec.return_value = result
    db_session.commit = AsyncMock(side_effect=IntegrityError("stmt", None, Exception("duplicate")))
    _install_session(db_session)

    response = client.patch(f"/api/v1/groups/{group.id}", json={"name": "開発系"})

    assert response.status_code == HTTPStatus.BAD_REQUEST
    db_session.rollback.assert_awaited_once()


def test_delete_group_returns_204() -> None:
    """自分のグループへの DELETE が 204 を返し、グループを削除することを確認するテスト."""
    group = SummaryGroup(user_id=_USER.id, name="営業系")
    result = MagicMock()
    result.first.return_value = group
    db_session = AsyncMock()
    db_session.exec.return_value = result
    _install_session(db_session)

    response = client.delete(f"/api/v1/groups/{group.id}")

    assert response.status_code == HTTPStatus.NO_CONTENT
    db_session.delete.assert_awaited_once_with(group)


def test_delete_group_returns_404_when_missing() -> None:
    """存在しない (または他人の) グループへの DELETE が 404 を返すことを確認するテスト."""
    result = MagicMock()
    result.first.return_value = None
    db_session = AsyncMock()
    db_session.exec.return_value = result
    _install_session(db_session)

    response = client.delete(f"/api/v1/groups/{uuid4()}")

    assert response.status_code == HTTPStatus.NOT_FOUND


def test_list_groups_requires_authentication() -> None:
    """未認証のときグループ一覧 GET が 401 を返すことを確認するテスト."""
    _install_session(AsyncMock())
    app.dependency_overrides.pop(get_current_user, None)

    response = client.get("/api/v1/groups")

    assert response.status_code == HTTPStatus.UNAUTHORIZED
