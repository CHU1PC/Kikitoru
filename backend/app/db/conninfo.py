from __future__ import annotations

from typing import TYPE_CHECKING

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
