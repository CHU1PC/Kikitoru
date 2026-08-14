"""add deleted_at to summaries.

Revision ID: 2780008cab58
Revises: 7cab7f45844c
Create Date: 2026-06-29 14:14:42.360170

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "2780008cab58"
down_revision: str | Sequence[str] | None = "7cab7f45844c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("summaries", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("summaries", "deleted_at")
