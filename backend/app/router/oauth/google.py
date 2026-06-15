import secrets
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token

from app.auth.identities import upsert_user_from_identity
from app.auth.user_sessions import SESSION_COOKIE, SESSION_MAX_AGE, create_user_session
from app.dependencies import DbSessionDep
from app.rate_limit import OAUTH_RATE_LIMIT, limiter
from app.settings.config import settings

router = APIRouter(prefix="/google")

_PROVIDER = "google"
_STATE_COOKIE = "oauth_state"
_STATE_MAX_AGE = 600  # seconds
_LOGIN_REDIRECT_URL = "/"  # 暫定: フロントエンド (issue #6) 実装後に差し替える
_GOOGLE_AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
_GOOGLE_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"  # noqa: S105


@router.get("/start")
@limiter.limit(OAUTH_RATE_LIMIT)  # pyright: ignore[reportUntypedFunctionDecorator, reportUnknownMemberType]
async def start_oauth(request: Request) -> RedirectResponse:  # noqa: ARG001
    """Googleの認可画面へリダイレクトしてCSRF対策のstateをCookieに保存する.

    Args:
        request (Request): The incoming request, used by the rate limiter.

    Returns:
        RedirectResponse: Googleの認可画面へのリダイレクト.
    """
    state = secrets.token_urlsafe(32)

    params: dict[str, str] = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
    }
    auth_url = f"{_GOOGLE_AUTH_ENDPOINT}?{urlencode(params)}"

    response = RedirectResponse(auth_url)
    response.set_cookie(
        key=_STATE_COOKIE,
        value=state,
        max_age=_STATE_MAX_AGE,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite="lax",
    )
    return response


@router.get("/callback")
@limiter.limit(OAUTH_RATE_LIMIT)  # pyright: ignore[reportUntypedFunctionDecorator, reportUnknownMemberType]
async def oauth_callback(
    request: Request, code: str, state: str, db_session: DbSessionDep
) -> RedirectResponse:
    """Googleの認可サーバーからのコールバックを処理してログインを成立させる.

    Args:
        request (Request): The incoming request, used to access cookies.
        code (str): The authorization code returned by Google.
        state (str): The state parameter returned by Google, should match the cookie.
        db_session (AsyncSession): Database session.

    Returns:
        RedirectResponse: ログイン成立後のフロントエンドへのリダイレクト.

    Raises:
        HTTPException: state 不一致は 400、トークン交換・ID token 検証の失敗は 400.
    """
    cookie_state = request.cookies.get(_STATE_COOKIE)
    if cookie_state is None or not secrets.compare_digest(cookie_state, state):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or missing state parameter. Possible CSRF attack.",
        )

    async with httpx.AsyncClient() as client:
        token_response = await client.post(
            _GOOGLE_TOKEN_ENDPOINT,
            data={
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET.get_secret_value(),
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": settings.GOOGLE_REDIRECT_URI,
            },
        )
    if not token_response.is_success:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to exchange authorization code for tokens.",
        )
    try:
        raw_id_token = token_response.json()["id_token"]
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Invalid token response from Google.",
        ) from exc

    try:
        claim = google_id_token.verify_oauth2_token(  # pyright: ignore[reportUnknownMemberType]
            raw_id_token,
            google_requests.Request(),
            audience=settings.GOOGLE_CLIENT_ID,
        )
        subject = claim["sub"]
    except (ValueError, KeyError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid ID token received from Google.",
        ) from exc

    user = await upsert_user_from_identity(
        db_session,
        provider=_PROVIDER,
        subject=subject,
        email=claim.get("email"),
        name=claim.get("name") or "",
    )
    token = await create_user_session(
        db_session,
        user.id,
        user_agent=request.headers.get("user-agent"),
        ip_address=request.client.host if request.client else None,
    )

    response = RedirectResponse(_LOGIN_REDIRECT_URL)
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        max_age=SESSION_MAX_AGE,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite="lax",
    )
    response.delete_cookie(
        _STATE_COOKIE,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite="lax",
    )
    return response
