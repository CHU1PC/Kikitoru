from __future__ import annotations

from typing import TYPE_CHECKING

from sqlmodel import col, select

from app.db.models import OAuthIdentity, User

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession


async def upsert_user_from_identity(
    db_session: AsyncSession,
    *,
    provider: str,
    subject: str,
    email: str | None,
    name: str,
) -> User:
    """外部 IdP の identity から User を取得し、無ければ User と OAuthIdentity を作成する関数.

    (provider, subject) で既存の OAuthIdentity を引き、見つかればその User を返す (既存ログイン)。
    見つからなければ User と OAuthIdentity を新規作成して返す (初回ログイン)。メールでの自動
    リンクは行わない (検証されていないメールでの乗っ取りを避けるため)。

    Args:
        db_session (AsyncSession): データベースセッション.
        provider (str): IdP 識別子 ('google' / 'github' など).
        subject (str): IdP 内でのユーザー識別子 (Google の sub など).
        email (str | None): IdP から取得したメール (取得できた場合のみ).
        name (str): IdP から取得した表示名.

    Returns:
        User: 既存または新規作成された User.
    """
    identity = (
        await db_session.exec(
            select(OAuthIdentity).where(
                col(OAuthIdentity.provider) == provider,
                col(OAuthIdentity.subject) == subject,
            )
        )
    ).first()

    if identity is not None:
        return (await db_session.exec(select(User).where(col(User.id) == identity.user_id))).one()

    user = User(email=email, name=name)
    db_session.add(user)
    await db_session.flush()
    db_session.add(
        OAuthIdentity(user_id=user.id, provider=provider, subject=subject, email=email)
    )
    await db_session.commit()
    return user
