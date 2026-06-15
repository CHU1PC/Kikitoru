from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from app.db.models import UserSession
from app.settings.config import settings

if TYPE_CHECKING:
    from uuid import UUID

    from sqlmodel.ext.asyncio.session import AsyncSession

_SESSION_TOKEN_BYTES = 32

# ログインセッションの Cookie 設定 (provider 非依存。発行・検証・削除で共有する).
SESSION_COOKIE = "session_token"
# Cookie の max-age と DB の UserSession.expires_at は同じ設定から導出して揃える.
SESSION_MAX_AGE = settings.SESSION_EXPIRY_DAYS * 24 * 60 * 60


def hash_user_session_token(token: str) -> str:
    """ログインセッションのトークンを SHA-256 でハッシュ化する関数.

    生のトークンは Cookie でクライアントに渡し、DB の UserSession.token_hash には
    このハッシュのみを保存する. これにより DB が漏洩しても生トークンは復元できず、
    セッションを乗っ取られない.

    Args:
        token (str): クライアントに渡す生のセッショントークン.

    Returns:
        str: トークンの SHA-256 hex ダイジェスト (UserSession.token_hash に保存する値).
    """
    return hashlib.sha256(token.encode()).hexdigest()


async def create_user_session(
    db_session: AsyncSession,
    user_id: UUID,
    *,
    user_agent: str | None = None,
    ip_address: str | None = None,
) -> str:
    """ユーザーのログインセッションを発行し、生のセッショントークンを返す関数.

    ランダムなトークンを生成し、その SHA-256 ハッシュを UserSession として保存する.
    生のトークンは戻り値としてのみ返され、保存はされない (呼び出し側が Cookie に載せる).

    Args:
        db_session (AsyncSession): データベースセッション.
        user_id (UUID): ログインセッションを発行する対象ユーザーの ID.
        user_agent (str | None): クライアントの User-Agent (任意).
        ip_address (str | None): クライアントの IP アドレス (任意).

    Returns:
        str: クライアントに渡す生のセッショントークン.
    """
    token = secrets.token_urlsafe(_SESSION_TOKEN_BYTES)
    db_session.add(
        UserSession(
            user_id=user_id,
            token_hash=hash_user_session_token(token),
            expires_at=datetime.now(UTC) + timedelta(days=settings.SESSION_EXPIRY_DAYS),
            user_agent=user_agent,
            ip_address=ip_address,
        )
    )
    await db_session.commit()
    return token
