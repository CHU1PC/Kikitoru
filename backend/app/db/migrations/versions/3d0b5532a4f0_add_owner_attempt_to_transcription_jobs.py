"""add owner_attempt to transcription_jobs.

Revision ID: 3d0b5532a4f0
Revises: 65a74d62bf61
Create Date: 2026-08-03 00:02:47.858487

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3d0b5532a4f0"
down_revision: str | Sequence[str] | None = "65a74d62bf61"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # 二重実行を防ぐ楽観ロックの version. 既存行は NULL = 未所有.
    op.add_column("transcription_jobs", sa.Column("owner_attempt", sa.Integer(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("transcription_jobs", "owner_attempt")
