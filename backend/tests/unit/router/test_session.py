from __future__ import annotations

from http import HTTPStatus
from uuid import uuid4

from fastapi.testclient import TestClient

from app.db.models import User
from app.dependencies import get_current_user
from main import app

client = TestClient(app)


def test_me_returns_current_user_public() -> None:
    """認証済みのとき /auth/me が現在ユーザーの公開情報を返すことを確認するテスト."""
    user = User(id=uuid4(), email="taro@example.com", name="Taro")
    app.dependency_overrides[get_current_user] = lambda: user

    response = client.get("/auth/me")

    assert response.status_code == HTTPStatus.OK
    body = response.json()
    assert body == {"id": str(user.id), "email": "taro@example.com", "name": "Taro"}
