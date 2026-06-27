import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel

from app.db.models import ActionItem, Decision, Summary, Topic, User, UserSession

_ALEMBIC_MODELS = (Summary, Topic, Decision, ActionItem, User, UserSession)


config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = SQLModel.metadata


def _get_database_url() -> str:
    """Read DATABASE_URL directly from the environment.

    Reading from os.environ instead of app.settings.config keeps migrations
    independent of LLM/STT env vars (GOOGLE_API_KEY, S3_BUCKET, etc.) so they
    can run in DB-only CI jobs. Also avoids passing the URL through
    configparser, which would interpolate '%' characters.

    Returns:
        str: The DATABASE_URL from the environment.

    Raises:
        RuntimeError: If DATABASE_URL is not set.
    """
    url = os.environ.get("DATABASE_URL")
    if not url:
        msg = "DATABASE_URL environment variable is required for migrations"
        raise RuntimeError(msg)
    return url


def run_migrations_offline() -> None:
    """Run migrations without a live DB connection."""
    context.configure(
        url=_get_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Run migrations against an already-established synchronous connection."""
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Create an async engine and run the migrations within a sync-bridged run."""
    connectable = create_async_engine(
        _get_database_url(),
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode with a live database connection."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
