"""add users and user_sessions tables, and summaries.user_id.

Revision ID: 8f160e537bc2
Revises: 2b103f58012b
Create Date: 2026-06-06 12:21:45.486348

This migration introduces auth-related tables (users, user_sessions) and adds
the owner reference (summaries.user_id) plus a composite UNIQUE on
(user_id, content_hash) for per-user idempotency.

Note: summaries.user_id is added as NOT NULL without backfill. This is safe
because dev / CI environments have no existing summary rows when this
migration runs. For a production rollout with existing summary rows, use
a 3-step pattern instead: add as nullable, backfill, then alter to NOT NULL.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "8f160e537bc2"
down_revision: str | Sequence[str] | None = "2b103f58012b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add users / user_sessions tables and summaries.user_id with composite UNIQUE."""
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("google_sub", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
        sa.UniqueConstraint("google_sub"),
    )
    op.create_table(
        "user_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index(
        op.f("ix_user_sessions_expires_at"), "user_sessions", ["expires_at"], unique=False
    )
    op.create_index(
        op.f("ix_user_sessions_user_id"), "user_sessions", ["user_id"], unique=False
    )

    op.add_column("summaries", sa.Column("user_id", sa.Uuid(), nullable=False))
    op.drop_index(op.f("ix_summaries_content_hash"), table_name="summaries")
    op.create_index(
        op.f("ix_summaries_content_hash"), "summaries", ["content_hash"], unique=False
    )
    op.create_index(op.f("ix_summaries_user_id"), "summaries", ["user_id"], unique=False)
    op.create_unique_constraint(
        "uq_summaries_user_content_hash", "summaries", ["user_id", "content_hash"]
    )
    op.create_foreign_key(
        "fk_summaries_user_id",
        "summaries",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    """Drop users / user_sessions tables and summaries.user_id."""
    op.drop_constraint("fk_summaries_user_id", "summaries", type_="foreignkey")
    op.drop_constraint("uq_summaries_user_content_hash", "summaries", type_="unique")
    op.drop_index(op.f("ix_summaries_user_id"), table_name="summaries")
    op.drop_index(op.f("ix_summaries_content_hash"), table_name="summaries")
    op.create_index(
        op.f("ix_summaries_content_hash"), "summaries", ["content_hash"], unique=True
    )
    op.drop_column("summaries", "user_id")
    op.drop_index(op.f("ix_user_sessions_user_id"), table_name="user_sessions")
    op.drop_index(op.f("ix_user_sessions_expires_at"), table_name="user_sessions")
    op.drop_table("user_sessions")
    op.drop_table("users")
