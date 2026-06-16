from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.db.models import Summary, User
from app.dependencies import get_current_user
from main import app

if TYPE_CHECKING:
    from collections.abc import Callable

client = TestClient(app)


def test_duplicate_user_content_hash_is_rejected(seed: Callable[..., None]) -> None:
    """同一ユーザー・同一 content_hash の summary 重複が複合 unique で拒否されることを確認するテスト."""
    user = User(email="owner@example.com", name="Owner")
    seed(user, Summary(user_id=user.id, filename="a.mp3", content_hash="dup", overall_summary="o1"))

    with pytest.raises(IntegrityError):
        seed(Summary(user_id=user.id, filename="b.mp3", content_hash="dup", overall_summary="o2"))


def test_same_content_hash_across_users_is_allowed(seed: Callable[..., None]) -> None:
    """別ユーザーなら同じ content_hash でも各自の summary として保存できることを確認するテスト."""
    user_a = User(email="a@example.com", name="A")
    user_b = User(email="b@example.com", name="B")
    seed(
        user_a,
        user_b,
        Summary(user_id=user_a.id, filename="a.mp3", content_hash="same", overall_summary="oa"),
        Summary(user_id=user_b.id, filename="b.mp3", content_hash="same", overall_summary="ob"),
    )

    app.dependency_overrides[get_current_user] = lambda: user_a
    assert client.get("/api/v1/summaries").json()["total"] == 1
    app.dependency_overrides[get_current_user] = lambda: user_b
    assert client.get("/api/v1/summaries").json()["total"] == 1
