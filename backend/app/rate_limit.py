from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import status
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.settings import settings

if TYPE_CHECKING:
    from fastapi import Request, Response

AUDIO_SUMMARIZE_RATE_LIMIT = "10/hour"
OAUTH_RATE_LIMIT = "10/minute"

# クライアント IP 単位でカウントする
limiter = Limiter(key_func=get_remote_address, storage_uri=settings.RATE_LIMIT_STORAGE_URI)


def rate_limit_exceeded_handler(_request: Request, _exc: Exception) -> Response:
    """レート制限超過時に 429 を返す例外ハンドラ.

    Args:
        _request (Request): 受信したリクエスト.
        _exc (RateLimitExceeded): slowapi が送出する超過例外.

    Returns:
        Response: detail を含む 429 の JSON レスポンス.
    """
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content={"detail": "Too many requests. Please try again later."},
    )
