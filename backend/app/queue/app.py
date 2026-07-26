from __future__ import annotations

from procrastinate import App, PsycopgConnector

from app.db.conninfo import psycopg_conninfo
from app.settings import settings

queue_app = App(
    connector=PsycopgConnector(
        conninfo=psycopg_conninfo(
            settings.DATABASE_URL.get_secret_value(), settings.DATABASE_SSL_MODE
        )
    ),
    import_paths=["app.queue.tasks"],
)
