from __future__ import annotations

from typing import TYPE_CHECKING

from app.auth.identities import upsert_user_from_identity

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from sqlmodel.ext.asyncio.session import AsyncSession

    from app.db.models import User


def _upsert(provider: str, subject: str, email: str, name: str) -> Callable[[AsyncSession], Awaitable[User]]:
    """指定の引数で upsert_user_from_identity を呼ぶ coroutine 関数を返すヘルパー.

    Args:
        provider (str): IdP 識別子.
        subject (str): IdP 内のユーザー識別子.
        email (str): メール.
        name (str): 表示名.

    Returns:
        Callable[[AsyncSession], Awaitable[User]]: session を受け取り upsert を実行する関数.
    """

    async def _run(session: AsyncSession) -> User:
        return await upsert_user_from_identity(session, provider=provider, subject=subject, email=email, name=name)

    return _run


def test_repeated_login_returns_same_user(db_call: Callable[..., User]) -> None:
    """同じ (provider, subject) で再ログインしても同一 User が返ることを確認するテスト."""
    first = db_call(_upsert("google", "sub-1", "x@example.com", "X"))
    second = db_call(_upsert("google", "sub-1", "x@example.com", "X"))

    assert first.id == second.id


def test_different_subject_creates_new_user(db_call: Callable[..., User]) -> None:
    """別の (provider, subject) は別 User として作成されることを確認するテスト."""
    one = db_call(_upsert("google", "sub-1", "a@example.com", "A"))
    two = db_call(_upsert("google", "sub-2", "b@example.com", "B"))

    assert one.id != two.id
