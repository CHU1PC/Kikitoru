"""add db queue columns to transcription_jobs.

Revision ID: 101d6fcdd23a
Revises: 7d69c708a14b
Create Date: 2026-08-04 14:16:07.663431

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "101d6fcdd23a"
down_revision: str | Sequence[str] | None = "7d69c708a14b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # 65a74d62bf61 で procrastinate に委ねた実行回数を自前キューに戻す.
    # 定数 default 付きなら PG 11+ はテーブルを書き換えない. model と DDL を揃えるため直後に落とす
    op.add_column(
        "transcription_jobs",
        sa.Column("attempts", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.alter_column("transcription_jobs", "attempts", server_default=None)

    # now() は volatile でテーブル書き換えを誘発するので, nullable で足して backfill する
    op.add_column(
        "transcription_jobs",
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute("UPDATE transcription_jobs SET scheduled_at = created_at")
    op.alter_column("transcription_jobs", "scheduled_at", nullable=False)

    # procrastinate の attempt 番号を版として使う代わりに, 取得ごとに発行する token で fencing する
    op.add_column("transcription_jobs", sa.Column("owner_token", sa.Uuid(), nullable=True))
    op.drop_column("transcription_jobs", "owner_attempt")

    op.create_index(
        "ix_transcription_jobs_ready",
        "transcription_jobs",
        ["scheduled_at", "created_at"],
        postgresql_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_transcription_jobs_ready", table_name="transcription_jobs")
    op.add_column("transcription_jobs", sa.Column("owner_attempt", sa.Integer(), nullable=True))
    op.drop_column("transcription_jobs", "owner_token")
    op.drop_column("transcription_jobs", "scheduled_at")
    op.drop_column("transcription_jobs", "attempts")
