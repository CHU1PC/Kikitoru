from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from http import HTTPStatus
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from fastapi.testclient import TestClient

from app.auth.user_sessions import SESSION_COOKIE
from app.db.models import User, UserSession
from app.dependencies import get_current_user
from app.router.oauth.session import logout
from main import app

client = TestClient(app)


def _db_session_with_session(user_session: object) -> AsyncMock:
    """exec().first() が指定の UserSession (または None) を返す DB セッションのモックを作る関数.

    Args:
        user_session (object): exec().first() が返す UserSession. None なら未登録.

    Returns:
        AsyncMock: logout が使う DB セッションのモック.
    """
    result = MagicMock()
    result.first.return_value = user_session
    db_session = AsyncMock()
    db_session.exec.return_value = result
    return db_session


def test_me_returns_current_user_public() -> None:
    """認証済みのとき /auth/me が現在ユーザーの公開情報を返すことを確認するテスト."""
    user = User(id=uuid4(), email="taro@example.com", name="Taro")
    app.dependency_overrides[get_current_user] = lambda: user

    response = client.get("/auth/me")

    assert response.status_code == HTTPStatus.OK
    body = response.json()
    assert body == {"id": str(user.id), "email": "taro@example.com", "name": "Taro"}


def test_logout_revokes_session_and_deletes_cookie() -> None:
    """有効なセッションのとき revoked_at を立て、Cookie を削除することを確認するテスト."""
    user_session = UserSession(user_id=uuid4(), token_hash="hash")  # noqa: S106
    db_session = _db_session_with_session(user_session)
    request = MagicMock()
    request.cookies.get.return_value = "token"
    response = MagicMock()

    asyncio.run(logout(request, response, db_session))

    assert user_session.revoked_at is not None
    db_session.commit.assert_awaited_once()
    response.delete_cookie.assert_called_once()
    assert response.delete_cookie.call_args.args[0] == SESSION_COOKIE


def test_logout_without_cookie_is_idempotent() -> None:
    """Cookie が無いとき DB に触れず Cookie 削除だけ行うことを確認するテスト."""
    db_session = _db_session_with_session(None)
    request = MagicMock()
    request.cookies.get.return_value = None
    response = MagicMock()

    asyncio.run(logout(request, response, db_session))

    db_session.exec.assert_not_called()
    db_session.commit.assert_not_awaited()
    response.delete_cookie.assert_called_once()


def test_logout_already_revoked_skips_commit() -> None:
    """既に取り消し済みのセッションでは commit せず Cookie 削除だけ行うことを確認するテスト."""
    revoked = UserSession(user_id=uuid4(), token_hash="hash", revoked_at=datetime.now(UTC))  # noqa: S106
    db_session = _db_session_with_session(revoked)
    request = MagicMock()
    request.cookies.get.return_value = "token"
    response = MagicMock()

    asyncio.run(logout(request, response, db_session))

    db_session.commit.assert_not_awaited()
    response.delete_cookie.assert_called_once()
