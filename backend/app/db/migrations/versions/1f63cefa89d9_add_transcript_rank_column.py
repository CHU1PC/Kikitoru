"""add transcript rank column.

Revision ID: 1f63cefa89d9
Revises: 803a7a025926
Create Date: 2026-07-01 12:40:58.498199

"""

from collections.abc import Sequence
from itertools import groupby

import sqlalchemy as sa
from alembic import op
from fractional_indexing import generate_n_keys_between

# revision identifiers, used by Alembic.
revision: str = "1f63cefa89d9"
down_revision: str | Sequence[str] | None = "803a7a025926"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add a time-seeded fractional rank column to transcript_segments."""
    op.add_column(
        "transcript_segments",
        sa.Column("rank", sa.String(length=64, collation="C"), nullable=True),
    )
    _backfill_ranks(op.get_bind())
    op.alter_column("transcript_segments", "rank", nullable=False)
    op.create_index(op.f("ix_transcript_segments_rank"), "transcript_segments", ["rank"], unique=False)


def downgrade() -> None:
    """Drop the rank column from transcript_segments."""
    op.drop_index(op.f("ix_transcript_segments_rank"), table_name="transcript_segments")
    op.drop_column("transcript_segments", "rank")


def _backfill_ranks(conn: sa.Connection) -> None:
    """Assign time-ordered fractional ranks to existing rows, per summary."""
    rows = conn.execute(
        sa.text("SELECT id, summary_id FROM transcript_segments ORDER BY summary_id, start_ms, id")
    ).all()
    for _summary_id, group in groupby(rows, key=lambda row: row.summary_id):
        ids = [row.id for row in group]
        ranks = generate_n_keys_between(None, None, len(ids))
        for seg_id, rank in zip(ids, ranks, strict=True):
            conn.execute(
                sa.text("UPDATE transcript_segments SET rank = :rank WHERE id = :id"),
                {"rank": rank, "id": seg_id},
            )
