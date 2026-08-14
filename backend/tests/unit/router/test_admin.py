from __future__ import annotations

from http import HTTPStatus
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from fastapi.testclient import TestClient

from app.db.engine import get_db_session
from app.db.models import User, UserRole, UserStatus
from app.dependencies import get_current_user
from main import app

if TYPE_CHECKING:
    from collections.abc import Generator

client = TestClient(app)

_ADMIN = User(
    id=uuid4(),
    email="admin@example.com",
    name="Admin",
    role=UserRole.admin,
    status=UserStatus.approved,
)


def _install_session(db_session: AsyncMock, *, current_user: User = _ADMIN) -> None:
    """db_session と current_user の override を登録する (後始末は conftest が行う).

    Args:
        db_session (AsyncMock): エンドポイントに注入するセッションのモック.
        current_user (User): ログイン中とみなすユーザー. 既定は admin.
    """

    def override_get_session() -> Generator[AsyncMock]:
        """テスト用セッションを yield する get_db_session の override.

        Yields:
            AsyncMock: テスト用セッションのモック.
        """
        yield db_session

    app.dependency_overrides[get_db_session] = override_get_session
    app.dependency_overrides[get_current_user] = lambda: current_user


def test_admin_users_rejects_non_admin() -> None:
    """非 admin (member) は admin ルートで 403 になる (router dependency)."""
    member = User(id=uuid4(), email="m@example.com", name="M", role=UserRole.user, status=UserStatus.approved)
    _install_session(AsyncMock(), current_user=member)

    response = client.get("/api/v1/admin/users")

    assert response.status_code == HTTPStatus.FORBIDDEN


def test_admin_users_rejects_unauthenticated() -> None:
    """未認証のとき admin ルートは 401 になる."""
    _install_session(AsyncMock())
    app.dependency_overrides.pop(get_current_user, None)

    response = client.get("/api/v1/admin/users")

    assert response.status_code == HTTPStatus.UNAUTHORIZED


def test_admin_list_users_returns_role_and_status() -> None:
    """Admin はユーザー一覧 (role/status 込み) を取得できる."""
    users = [
        User(id=uuid4(), email="a@example.com", name="A", role=UserRole.user, status=UserStatus.pending),
        User(id=uuid4(), email="b@example.com", name="B", role=UserRole.admin, status=UserStatus.approved),
    ]
    result = MagicMock()
    result.all.return_value = users
    db_session = AsyncMock()
    db_session.exec.return_value = result
    _install_session(db_session)

    response = client.get("/api/v1/admin/users")

    assert response.status_code == HTTPStatus.OK
    body = response.json()
    assert [u["email"] for u in body] == ["a@example.com", "b@example.com"]
    assert body[0]["status"] == "pending"
    assert body[1]["role"] == "admin"


def test_admin_list_users_accepts_status_filter() -> None:
    """?status= で絞り込みクエリを受け付ける (alias が効く)."""
    result = MagicMock()
    result.all.return_value = []
    db_session = AsyncMock()
    db_session.exec.return_value = result
    _install_session(db_session)

    response = client.get("/api/v1/admin/users", params={"status": "pending"})

    assert response.status_code == HTTPStatus.OK


def test_admin_patch_approves_user() -> None:
    """PATCH status=approved で pending ユーザーを承認できる."""
    target = User(id=uuid4(), email="t@example.com", name="T", role=UserRole.user, status=UserStatus.pending)
    db_session = AsyncMock()
    db_session.get.return_value = target
    _install_session(db_session)

    response = client.patch(f"/api/v1/admin/users/{target.id}", json={"status": "approved"})

    assert response.status_code == HTTPStatus.OK
    assert response.json()["status"] == "approved"
    db_session.commit.assert_awaited_once()


def test_admin_patch_promotes_user() -> None:
    """PATCH role=admin でユーザーを管理者に昇格できる."""
    target = User(id=uuid4(), email="t@example.com", name="T", role=UserRole.user, status=UserStatus.approved)
    db_session = AsyncMock()
    db_session.get.return_value = target
    _install_session(db_session)

    response = client.patch(f"/api/v1/admin/users/{target.id}", json={"role": "admin"})

    assert response.status_code == HTTPStatus.OK
    assert response.json()["role"] == "admin"


def test_admin_patch_returns_404_for_missing_user() -> None:
    """存在しないユーザーへの PATCH は 404."""
    db_session = AsyncMock()
    db_session.get.return_value = None
    _install_session(db_session)

    response = client.patch(f"/api/v1/admin/users/{uuid4()}", json={"status": "approved"})

    assert response.status_code == HTTPStatus.NOT_FOUND


def test_admin_patch_self_demote_is_rejected() -> None:
    """Admin が自分自身を demote (role=user) しようとすると 400 (ロックアウト防止)."""
    db_session = AsyncMock()
    db_session.get.return_value = _ADMIN
    _install_session(db_session)

    response = client.patch(f"/api/v1/admin/users/{_ADMIN.id}", json={"role": "user"})

    assert response.status_code == HTTPStatus.BAD_REQUEST


def test_admin_patch_self_reject_is_rejected() -> None:
    """Admin が自分自身を reject (status=rejected) しようとすると 400."""
    db_session = AsyncMock()
    db_session.get.return_value = _ADMIN
    _install_session(db_session)

    response = client.patch(f"/api/v1/admin/users/{_ADMIN.id}", json={"status": "rejected"})

    assert response.status_code == HTTPStatus.BAD_REQUEST
