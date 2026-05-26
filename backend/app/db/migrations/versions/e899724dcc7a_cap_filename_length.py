"""cap filename length

Revision ID: e899724dcc7a
Revises: 65436f77ed6b
Create Date: 2026-05-19 14:43:47.225037

"""
from collections.abc import Sequence

import sqlmodel
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e899724dcc7a"
down_revision: str | Sequence[str] | None = "65436f77ed6b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Cap summaries.filename to 255 characters.

    Truncate any existing rows whose filename exceeds 255 chars before
    altering the column so the ALTER does not fail with
    'value too long for type character varying(255)'.
    """
    op.execute("UPDATE summaries SET filename = LEFT(filename, 255) WHERE LENGTH(filename) > 255")
    op.alter_column(
        "summaries",
        "filename",
        existing_type=sqlmodel.sql.sqltypes.AutoString(),
        type_=sqlmodel.sql.sqltypes.AutoString(length=255),
        existing_nullable=False,
    )


def downgrade() -> None:
    """Revert summaries.filename back to unbounded text."""
    op.alter_column(
        "summaries",
        "filename",
        existing_type=sqlmodel.sql.sqltypes.AutoString(length=255),
        type_=sqlmodel.sql.sqltypes.AutoString(),
        existing_nullable=False,
    )
