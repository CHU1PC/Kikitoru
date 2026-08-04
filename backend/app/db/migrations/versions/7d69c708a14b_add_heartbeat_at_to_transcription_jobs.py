"""add heartbeat_at to transcription_jobs.

Revision ID: 7d69c708a14b
Revises: 3d0b5532a4f0
Create Date: 2026-08-03 13:52:42.609379

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7d69c708a14b"
down_revision: str | Sequence[str] | None = "3d0b5532a4f0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # 孤児検出を経過時間でなく worker の生存信号で判定するために使う
    op.add_column(
        "transcription_jobs",
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("transcription_jobs", "heartbeat_at")
