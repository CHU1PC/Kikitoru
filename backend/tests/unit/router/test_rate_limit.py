from __future__ import annotations

from http import HTTPStatus

from fastapi.testclient import TestClient

from app.rate_limit import OAUTH_RATE_LIMIT
from main import app

client = TestClient(app)


def test_oauth_start_blocks_after_exceeding_rate_limit() -> None:
    """OAUTH_RATE_LIMIT を超えて /auth/google/start を叩くと 429 を返すことを確認するテスト.

    上限までは認可画面へのリダイレクト、上限を超えた1回だけ 429 になることを検証する.
    """
    # "10/minute" のような制限文字列から許可回数 (10) を取り出す.
    allowed = int(OAUTH_RATE_LIMIT.split("/")[0])

    statuses = [
        client.get("/auth/google/start", follow_redirects=False).status_code for _ in range(allowed)
    ]
    blocked = client.get("/auth/google/start", follow_redirects=False)

    assert all(code == HTTPStatus.TEMPORARY_REDIRECT for code in statuses)
    assert blocked.status_code == HTTPStatus.TOO_MANY_REQUESTS
    assert blocked.json() == {"detail": "Too many requests. Please try again later."}
