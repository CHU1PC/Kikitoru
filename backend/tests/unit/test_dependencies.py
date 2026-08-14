from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.db.models import User, UserSession
from app.dependencies import get_current_user


def _request_with_token(token: str | None) -> MagicMock:
    """指定したセッショントークンを Cookie に持つリクエストのモックを作る関数.

    Args:
        token (str | None): Cookie から返すトークン. None なら Cookie 無しを表す.

    Returns:
        MagicMock: cookies.get がそのトークンを返すリクエストのモック.
    """
    request = MagicMock()
    request.cookies.get.return_value = token
    return request


def _db_session_with(user_session: object, user: object) -> AsyncMock:
    """exec().first() と get() の戻り値を仕込んだ DB セッションのモックを作る関数.

    Args:
        user_session (object): exec().first() が返す UserSession (または None).
        user (object): get() が返す User (または None).

    Returns:
        AsyncMock: get_current_user が使う DB セッションのモック.
    """
    result = MagicMock()
    result.first.return_value = user_session
    db_session = AsyncMock()
    db_session.exec.return_value = result
    db_session.get.return_value = user
    return db_session


def test_returns_user_for_valid_session() -> None:
    """有効なセッションのとき現在の User を返すことを確認するテスト."""
    user = User(id=uuid4(), email="taro@example.com", name="Taro")
    user_session = UserSession(user_id=user.id, token_hash="hash")  # ruff:ignore[hardcoded-password-func-arg]
    db_session = _db_session_with(user_session, user)

    result = asyncio.run(get_current_user(_request_with_token("token"), db_session))

    assert result is user


def test_raises_401_when_cookie_missing() -> None:
    """セッション Cookie が無いとき 401 を送出することを確認するテスト."""
    db_session = _db_session_with(None, None)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(get_current_user(_request_with_token(None), db_session))

    assert exc.value.status_code == HTTPStatus.UNAUTHORIZED


def test_raises_401_when_session_not_found() -> None:
    """トークンに対応する UserSession が無いとき 401 を送出することを確認するテスト."""
    db_session = _db_session_with(None, None)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(get_current_user(_request_with_token("token"), db_session))

    assert exc.value.status_code == HTTPStatus.UNAUTHORIZED


def test_raises_401_when_session_revoked() -> None:
    """セッションが取り消し済みのとき 401 を送出することを確認するテスト."""
    user = User(id=uuid4(), email="taro@example.com", name="Taro")
    user_session = UserSession(user_id=user.id, token_hash="hash", revoked_at=datetime.now(UTC))  # ruff:ignore[hardcoded-password-func-arg]
    db_session = _db_session_with(user_session, user)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(get_current_user(_request_with_token("token"), db_session))

    assert exc.value.status_code == HTTPStatus.UNAUTHORIZED


def test_raises_401_when_session_expired() -> None:
    """セッションが期限切れのとき 401 を送出することを確認するテスト."""
    user = User(id=uuid4(), email="taro@example.com", name="Taro")
    expired = datetime.now(UTC) - timedelta(days=1)
    user_session = UserSession(user_id=user.id, token_hash="hash", expires_at=expired)  # ruff:ignore[hardcoded-password-func-arg]
    db_session = _db_session_with(user_session, user)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(get_current_user(_request_with_token("token"), db_session))

    assert exc.value.status_code == HTTPStatus.UNAUTHORIZED


def test_raises_401_when_user_missing() -> None:
    """セッションは有効だが User が存在しないとき 401 を送出することを確認するテスト."""
    user_session = UserSession(user_id=uuid4(), token_hash="hash")  # ruff:ignore[hardcoded-password-func-arg]
    db_session = _db_session_with(user_session, None)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(get_current_user(_request_with_token("token"), db_session))

    assert exc.value.status_code == HTTPStatus.UNAUTHORIZED
