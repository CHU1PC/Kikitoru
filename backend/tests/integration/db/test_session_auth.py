from __future__ import annotations

from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from typing import TYPE_CHECKING

from fastapi.testclient import TestClient

from app.auth.user_sessions import SESSION_COOKIE, create_user_session, hash_user_session_token
from app.db.models import User, UserSession
from main import app

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlmodel.ext.asyncio.session import AsyncSession

client = TestClient(app)


def test_valid_session_cookie_authenticates(db_call: Callable[..., tuple[str, str]]) -> None:
    """有効なセッション Cookie で /auth/me が現在ユーザーを返すことを確認するテスト."""

    async def _setup(session: AsyncSession) -> tuple[str, str]:
        user = User(email="owner@example.com", name="Owner")
        session.add(user)
        await session.flush()
        token = await create_user_session(session, user.id)
        return str(user.id), token

    user_id, token = db_call(_setup)
    client.cookies.set(SESSION_COOKIE, token)
    try:
        response = client.get("/auth/me")
    finally:
        client.cookies.clear()

    assert response.status_code == HTTPStatus.OK
    assert response.json()["id"] == user_id


def test_expired_session_is_rejected(db_call: Callable[..., str]) -> None:
    """期限切れのセッション Cookie では /auth/me が 401 になることを確認するテスト."""
    raw_token = "expired-token"  # ruff:ignore[hardcoded-password-string]

    async def _setup(session: AsyncSession) -> str:
        user = User(email="owner@example.com", name="Owner")
        session.add(user)
        await session.flush()
        session.add(
            UserSession(
                user_id=user.id,
                token_hash=hash_user_session_token(raw_token),
                expires_at=datetime.now(UTC) - timedelta(days=1),
            )
        )
        await session.commit()
        return raw_token

    token = db_call(_setup)
    client.cookies.set(SESSION_COOKIE, token)
    try:
        response = client.get("/auth/me")
    finally:
        client.cookies.clear()

    assert response.status_code == HTTPStatus.UNAUTHORIZED
