from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.auth.user_sessions import SESSION_COOKIE, hash_user_session_token
from app.db.engine import get_db_session
from app.db.models import User, UserSession

DbSessionDep = Annotated[AsyncSession, Depends(get_db_session)]


async def get_current_user(request: Request, db_session: DbSessionDep) -> User:
    """Cookie のセッショントークンから現在ログイン中の User を復元する FastAPI 依存性.

    session_token Cookie をハッシュ化して UserSession を引き、有効 (取り消し・期限切れでない)
    なら紐づく User を返す. 認証が必要なエンドポイントで `user: CurrentUser` として注入する.

    Args:
        request (Request): セッション Cookie を読むためのリクエスト.
        db_session (AsyncSession): Database session.

    Returns:
        User: 現在ログイン中のユーザー.

    Raises:
        HTTPException: トークンが無い・無効・期限切れ、または User が存在しない場合は 401.
    """
    token = request.cookies.get(SESSION_COOKIE)
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    token_hash = hash_user_session_token(token)
    user_session = (
        await db_session.exec(select(UserSession).where(col(UserSession.token_hash) == token_hash))
    ).first()
    if (
        user_session is None
        or user_session.revoked_at is not None
        or user_session.expires_at <= datetime.now(UTC)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session",
        )

    user = await db_session.get(User, user_session.user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session",
        )
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
