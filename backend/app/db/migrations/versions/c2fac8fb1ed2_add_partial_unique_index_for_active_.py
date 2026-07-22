"""add partial unique index for active transcription jobs.

Revision ID: c2fac8fb1ed2
Revises: 428e50631841
Create Date: 2026-07-10 13:30:03.566010

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c2fac8fb1ed2"
down_revision: str | Sequence[str] | None = "428e50631841"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # 進行中(pending/processing)のジョブは (user_id, content_hash) で一意にし, 同時二重投稿の
    # 二重課金を防ぐ。completed/failed は対象外なので, 過去分や再アップの新規作成は妨げない。
    op.create_index(
        "uq_transcription_jobs_active_hash",
        "transcription_jobs",
        ["user_id", "content_hash"],
        unique=True,
        postgresql_where=sa.text("status IN ('pending', 'processing')"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("uq_transcription_jobs_active_hash", table_name="transcription_jobs")
