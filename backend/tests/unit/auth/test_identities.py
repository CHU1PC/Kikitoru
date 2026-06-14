from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from app.auth.identities import upsert_user_from_identity
from app.db.models import OAuthIdentity, User


def _db_session(existing_identity: object) -> AsyncMock:
    """exec().first() が指定の OAuthIdentity (または None) を返す DB セッションのモックを作る関数.

    Args:
        existing_identity (object): exec().first() が返す既存の OAuthIdentity. None なら未登録.

    Returns:
        AsyncMock: upsert_user_from_identity が使う DB セッションのモック.
    """
    result = MagicMock()
    result.first.return_value = existing_identity
    db_session = AsyncMock()
    db_session.add = MagicMock()
    db_session.exec.return_value = result
    return db_session


def test_returns_existing_user_when_identity_found() -> None:
    """既存の (provider, subject) があるとき新規作成せず既存 User を返すことを確認するテスト."""
    existing_user = User(id=uuid4(), email="taro@example.com", name="Taro")
    identity = OAuthIdentity(user_id=existing_user.id, provider="google", subject="sub-1")
    db_session = _db_session(existing_identity=identity)
    db_session.exec.return_value.one.return_value = existing_user

    result = asyncio.run(
        upsert_user_from_identity(
            db_session, provider="google", subject="sub-1", email="taro@example.com", name="Taro"
        )
    )

    assert result is existing_user
    db_session.add.assert_not_called()


def test_creates_user_and_identity_on_first_login() -> None:
    """未登録の (provider, subject) のとき User と OAuthIdentity を新規作成することを確認するテスト."""
    db_session = _db_session(existing_identity=None)

    result = asyncio.run(
        upsert_user_from_identity(
            db_session, provider="google", subject="new-sub", email="hanako@example.com", name="Hanako"
        )
    )

    assert isinstance(result, User)
    assert result.email == "hanako@example.com"
    added = [call.args[0] for call in db_session.add.call_args_list]
    assert any(isinstance(obj, User) for obj in added)
    assert any(isinstance(obj, OAuthIdentity) for obj in added)
    db_session.commit.assert_awaited_once()
