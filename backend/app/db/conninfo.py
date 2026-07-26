from __future__ import annotations

from typing import TYPE_CHECKING

from psycopg.conninfo import make_conninfo
from sqlalchemy.engine import make_url

if TYPE_CHECKING:
    from sqlalchemy.engine.url import URL


def sqlalchemy_url_with_sslmode(url_str: str, default_sslmode: str) -> URL:
    """URL に sslmode がなければ default を追加した SQLAlchemy URLを返す.

    Args:
        url_str (str): SQLAlchemy 形式 URL.
        default_sslmode (str): URL 未指定時のフォールバック sslmode.

    Returns:
        URL: sslmode をマージ済みの SQLAlchemy URL.
    """
    url = make_url(url_str)
    if "sslmode" in url.query:
        return url
    return url.set(query={**url.query, "sslmode": default_sslmode})


def psycopg_conninfo(url_str: str, default_sslmode: str) -> str:
    """SQLAlchemy URL から libpq conninfo 文字列を組み立てる (URL の sslmode があれば尊重).

    Args:
        url_str (str): SQLAlchemy 形式 URL.
        default_sslmode (str): URL 未指定時のフォールバック sslmode.

    Returns:
        str: libpq 形式の conninfo 文字列.
    """
    url = make_url(url_str)
    query: dict[str, str] = {
        k: v if isinstance(v, str) else v[-1]
        for k, v in url.query.items()
    }
    query.setdefault("sslmode", default_sslmode)
    kwargs: dict[str, str | None] = {
        "host": url.host,
        "port": str(url.port) if url.port is not None else None,
        "user": url.username,
        "password": url.password,
        "dbname": url.database,
        **query,
    }
    return make_conninfo(**{k: v for k, v in kwargs.items() if v is not None})
