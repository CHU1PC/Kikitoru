from datetime import UTC, datetime

from fastapi import APIRouter, Request, Response, status
from sqlmodel import col, select

from app.auth.user_sessions import SESSION_COOKIE, hash_user_session_token
from app.db.models import UserSession
from app.dependencies import CurrentUser, DbSessionDep
from app.schema.users import UserPublic
from app.settings import settings

router = APIRouter()


@router.get("/me")
async def get_me(user: CurrentUser) -> UserPublic:
    """現在ログイン中のユーザーを返す.

    Args:
        user (User): セッション Cookie から復元された現在のユーザー.

    Returns:
        UserPublic: 公開してよいユーザープロフィール.
    """
    return UserPublic.model_validate(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, response: Response, db_session: DbSessionDep) -> None:
    """現在のセッションを失効させて session_token Cookie を削除する.

    Cookie のトークンに対応する UserSession があれば revoked_at を立てる. トークンが
    無効・期限切れでも 401 にはせず Cookie を消して成功扱いにする (冪等なログアウト).

    Args:
        request (Request): セッション Cookie を読むためのリクエスト.
        response (Response): Cookie を削除するためのレスポンス.
        db_session (AsyncSession): Database session.
    """
    token = request.cookies.get(SESSION_COOKIE)
    if token is not None:
        token_hash = hash_user_session_token(token)
        user_session = (
            await db_session.exec(select(UserSession).where(col(UserSession.token_hash) == token_hash))
        ).first()

        if user_session is not None and user_session.revoked_at is None:
            user_session.revoked_at = datetime.now(UTC)
            await db_session.commit()

    response.delete_cookie(
        SESSION_COOKIE,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite="lax",
    )
