from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from app.auth.user_sessions import create_user_session, hash_user_session_token
from app.db.models import UserSession


def test_create_user_session_stores_hashed_token_and_returns_raw() -> None:
    """生トークンを返しつつ DB にはそのハッシュを持つ UserSession を保存することを確認するテスト."""
    db_session = AsyncMock()
    db_session.add = MagicMock()
    user_id = uuid4()

    token = asyncio.run(create_user_session(db_session, user_id, user_agent="UA", ip_address="1.2.3.4"))

    added = db_session.add.call_args.args[0]
    assert isinstance(added, UserSession)
    assert added.user_id == user_id
    assert added.token_hash == hash_user_session_token(token)
    assert added.token_hash != token
    db_session.commit.assert_awaited_once()


def test_create_user_session_generates_unique_tokens() -> None:
    """呼び出しごとに異なるトークンが生成されることを確認するテスト."""
    db_session = AsyncMock()
    db_session.add = MagicMock()

    token_a = asyncio.run(create_user_session(db_session, uuid4()))
    token_b = asyncio.run(create_user_session(db_session, uuid4()))

    assert token_a != token_b
