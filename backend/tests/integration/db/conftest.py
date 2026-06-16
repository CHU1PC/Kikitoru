from __future__ import annotations

import asyncio
import os
import subprocess  # noqa: S404 -- alembic upgrade を固定引数で起動するためにのみ使う
import sys
from pathlib import Path
from typing import TYPE_CHECKING, cast
from unittest.mock import MagicMock

import pytest
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db.engine import get_db_session

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Awaitable, Callable, Generator, Sequence

# main は audio router 経由で torch 等の ML 依存を import するため、CI (ML 依存なし) でも
# テストモジュールが `from main import app` できるよう、先にモック化しておく (db テストは STT を呼ばない).
sys.modules.update({
    "torch": MagicMock(),
    "torchaudio": MagicMock(),
    "torchaudio.functional": MagicMock(),
    "faster_whisper": MagicMock(),
    "pyannote": MagicMock(),
    "pyannote.audio": MagicMock(),
})

from main import app  # noqa: E402 - 上記 ML モック後に import する必要があるため

# backend/ ディレクトリ (alembic.ini の場所)
_BACKEND_DIR = Path(__file__).resolve().parents[3]

# テスト DB の接続先。ローカルは docker-compose.test.yml の db-test (5433/kikitoru_test)、
# CI は service container を TEST_DATABASE_URL で渡す。
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://postgres:test_password@localhost:5433/kikitoru_test",
)

_engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)


def _db_reachable() -> bool:
    """テスト DB に接続できるかを確認する関数.

    Returns:
        bool: 接続できれば True、できなければ False (ローカルで未起動など).
    """

    async def _ping() -> None:
        async with _engine.connect() as conn:
            await conn.execute(text("SELECT 1"))

    try:
        asyncio.run(_ping())
    except (SQLAlchemyError, OSError):
        return False
    return True


@pytest.fixture(scope="session", autouse=True)  # noqa: RUF076 - DB 結合テスト全体で1回スキーマを用意する必要があるため autouse が適切
def migrate_test_db() -> None:
    """テスト DB に alembic upgrade head を流してスキーマを用意する session フィクスチャ.

    実マイグレーションを流すので「migration が空 DB で組めること」の軽い検証も兼ねる.
    テスト DB に繋げない (ローカルで未起動) 場合は、エラーにせず skip する.
    """
    if not _db_reachable():
        pytest.skip(
            "test DB に接続できません。`docker compose -f docker-compose.test.yml up -d` で起動してください",
        )
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=_BACKEND_DIR,
        env={**os.environ, "DATABASE_URL": TEST_DATABASE_URL},
        check=True,
    )


async def _truncate_all() -> None:
    """全テーブルを TRUNCATE してデータを消す関数 (alembic_version は metadata 外なので残る)."""
    tables = ", ".join(table.name for table in reversed(SQLModel.metadata.sorted_tables))
    async with _engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))


@pytest.fixture(autouse=True)  # noqa: RUF076 - 各テスト後に必ずデータを消す必要があるため autouse が適切
def truncate_between_tests() -> Generator[None]:
    """各テスト後に全テーブルを TRUNCATE し、テスト間でデータが混ざらないようにするフィクスチャ.

    Yields:
        None: テスト本体に制御を返すためのジェネレーター.
    """
    yield
    asyncio.run(_truncate_all())


@pytest.fixture(autouse=True)  # noqa: RUF076 - 全 DB テストで get_db_session を差し替える必要があるため autouse が適切
def override_db_session() -> Generator[None]:
    """App の get_db_session をテスト DB のセッションに差し替えるフィクスチャ.

    リクエストごとに NullPool から新規セッションを作るので、TestClient の各リクエストが
    自分のイベントループ内でコネクションを張る (ループ跨ぎを避ける).

    Yields:
        None: テスト本体に制御を返すためのジェネレーター.
    """

    async def _get_test_session() -> AsyncGenerator[AsyncSession]:
        session = AsyncSession(_engine)
        try:
            yield session
        finally:
            await session.close()

    app.dependency_overrides[get_db_session] = _get_test_session
    yield
    app.dependency_overrides.clear()


async def _insert_all_in_test_session(objects: Sequence[SQLModel]) -> None:
    """渡した objects を FK 親→子順に並べ替え、1件ずつ flush してテスト DB に保存する.

    Args:
        objects (Sequence[SQLModel]): 保存するモデルインスタンス列.
    """
    # sorted_tables は FK 依存順 (親が先)。テーブル名でその順に並べ替えてから1件ずつ flush する。
    order = {table.name: index for index, table in enumerate(SQLModel.metadata.sorted_tables)}
    ordered = sorted(objects, key=lambda obj: order[cast("str", obj.__tablename__)])  # pyright: ignore[reportUnknownMemberType]
    async with AsyncSession(_engine, expire_on_commit=False) as session:
        for obj in ordered:
            session.add(obj)
            await session.flush()
        await session.commit()


def _seed(*objects: SQLModel) -> None:
    """渡したモデルをテスト DB に保存する (FK 親→子順に自動ソート・同期実行).

    Args:
        *objects (SQLModel): 保存するモデルインスタンス (可変個).
    """
    asyncio.run(_insert_all_in_test_session(objects))


@pytest.fixture
def seed() -> Callable[..., None]:
    """テスト DB にモデルインスタンスを保存するヘルパーを返すフィクスチャ.

    FK の親→子の順 (users → summaries → ...) に自動で並べ替えて1件ずつ flush するので、
    渡す順序は気にしなくてよい。expire_on_commit=False なので commit 後もオブジェクトの
    id などの属性をテスト側で読める (assert や get_current_user の差し替えに使うため).

    Returns:
        Callable[..., None]: 可変個のモデルを受け取り、テスト DB に保存する関数.
    """
    return _seed


async def _run_in_test_session[T](fn: Callable[[AsyncSession], Awaitable[T]]) -> T:
    """テスト DB セッションを開いて fn に渡し、その結果を返す (NullPool で毎回新規接続).

    Args:
        fn (Callable[[AsyncSession], Awaitable[T]]): session を受け取り値を返す async 関数.

    Returns:
        T: fn が返した値.
    """
    async with AsyncSession(_engine, expire_on_commit=False) as session:
        return await fn(session)


def _call_in_test_session[T](fn: Callable[[AsyncSession], Awaitable[T]]) -> T:
    """テスト DB セッションで fn を同期的に実行し、結果を返す.

    Args:
        fn (Callable[[AsyncSession], Awaitable[T]]): session を受け取り何らかの値を返す async 関数.

    Returns:
        T: fn が返す値の型.
    """
    return asyncio.run(_run_in_test_session(fn))


@pytest.fixture
def db_call() -> Callable[..., object]:
    """Session を受け取る async 関数をテスト DB セッションで実行するヘルパーを返すフィクスチャ.

    upsert_user_from_identity / create_user_session など、内部の async 関数を実 DB に対して
    直接呼ぶテストで使う (expire_on_commit=False なので戻り値の属性も後で読める).

    Returns:
        Callable: coroutine 関数を受け取り、テスト DB セッションで実行して結果を返す関数.
    """
    return _call_in_test_session
