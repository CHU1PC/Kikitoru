"""drop attempts from transcription_jobs.

Revision ID: 65a74d62bf61
Revises: b45ad4f9f69c
Create Date: 2026-07-25 20:50:14.907235

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "65a74d62bf61"
down_revision: str | Sequence[str] | None = "b45ad4f9f69c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # retry 判定は procrastinate 側の attempts (procrastinate_jobs.attempts) に一本化するので
    # 自前カラムは削除する. mark_failed は procrastinate の context.job.attempts を使って
    # is_final を判定する.
    op.drop_column("transcription_jobs", "attempts")


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column(
        "transcription_jobs",
        sa.Column("attempts", sa.INTEGER(), server_default=sa.text("0"), nullable=False),
    )
