from __future__ import annotations

from procrastinate import App, PsycopgConnector

from app.settings import settings


def _to_psycopg_conninfo(sqlalchemy_url: str, sslmode: str) -> str:
    """SQLAlchemy URL を psycopg conninfo (libpq) 形式に変換する.

    Args:
        sqlalchemy_url (str): SQLAlchemy URL.
        sslmode (str): SSL モード. disable or verify-full.

    Returns:
        str: psycopg conninfo 形式の文字列.
    """
    base = sqlalchemy_url.replace("postgresql+psycopg://", "postgresql://")
    separator = "&" if "?" in base else "?"
    return f"{base}{separator}sslmode={sslmode}"


queue_app = App(
    connector=PsycopgConnector(
        conninfo=_to_psycopg_conninfo(
            settings.DATABASE_URL.get_secret_value(), settings.DATABASE_SSL_MODE
        ),
    ),
)
