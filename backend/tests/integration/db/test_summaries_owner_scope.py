from __future__ import annotations

from http import HTTPStatus
from typing import TYPE_CHECKING

from fastapi.testclient import TestClient

from app.db.models import Summary, User, UserStatus
from app.dependencies import get_current_user
from main import app

if TYPE_CHECKING:
    from collections.abc import Callable

client = TestClient(app)


def test_get_other_users_summary_returns_404(seed: Callable[..., None]) -> None:
    """他ユーザーの summary を ID 指定で取得しても 404 になる (実 DB での IDOR 検証) テスト."""
    owner = User(email="owner@example.com", name="Owner", status=UserStatus.approved)
    other = User(email="other@example.com", name="Other", status=UserStatus.approved)
    summary = Summary(user_id=owner.id, filename="secret.mp3", content_hash="h1", overall_summary="secret")
    seed(owner, other, summary)

    app.dependency_overrides[get_current_user] = lambda: other

    response = client.get(f"/api/v1/summaries/{summary.id}")

    assert response.status_code == HTTPStatus.NOT_FOUND


def test_get_own_summary_returns_detail(seed: Callable[..., None]) -> None:
    """自分の summary は ID 指定で取得できる (owner スコープが本人には効く) テスト."""
    owner = User(email="owner@example.com", name="Owner", status=UserStatus.approved)
    summary = Summary(user_id=owner.id, filename="mine.mp3", content_hash="h1", overall_summary="mine")
    seed(owner, summary)

    app.dependency_overrides[get_current_user] = lambda: owner

    response = client.get(f"/api/v1/summaries/{summary.id}")

    assert response.status_code == HTTPStatus.OK
    assert response.json()["filename"] == "mine.mp3"


def test_list_returns_only_own_summaries(seed: Callable[..., None]) -> None:
    """一覧は自分の summary だけを返し、他人の分は出ない (実 DB での絞り込み検証) テスト."""
    owner = User(email="owner@example.com", name="Owner", status=UserStatus.approved)
    other = User(email="other@example.com", name="Other", status=UserStatus.approved)
    mine = Summary(user_id=owner.id, filename="mine.mp3", content_hash="h1", overall_summary="mine")
    theirs = Summary(user_id=other.id, filename="theirs.mp3", content_hash="h2", overall_summary="theirs")
    seed(owner, other, mine, theirs)

    app.dependency_overrides[get_current_user] = lambda: owner

    response = client.get("/api/v1/summaries")

    assert response.status_code == HTTPStatus.OK
    body = response.json()
    assert [item["filename"] for item in body["items"]] == ["mine.mp3"]
    assert body["total"] == 1
