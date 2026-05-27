"""add content_hash to summaries.

Revision ID: 2b103f58012b
Revises: e899724dcc7a
Create Date: 2026-05-26 21:04:16.299398

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "2b103f58012b"
down_revision: str | Sequence[str] | None = "e899724dcc7a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add a nullable, unique content_hash column for upload idempotency.

    Nullable so existing rows (which have no associated audio hash) stay valid;
    Postgres treats multiple NULLs as distinct, so the unique index permits any
    number of hash-less rows while still rejecting duplicate real hashes.
    """
    op.add_column(
        "summaries",
        sa.Column("content_hash", sa.String(length=64), nullable=True),
    )
    op.create_index(
        op.f("ix_summaries_content_hash"),
        "summaries",
        ["content_hash"],
        unique=True,
    )


def downgrade() -> None:
    """Drop the content_hash column and its unique index."""
    op.drop_index(op.f("ix_summaries_content_hash"), table_name="summaries")
    op.drop_column("summaries", "content_hash")
