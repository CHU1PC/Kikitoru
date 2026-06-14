"""replace google_sub with oauth_identities.

Revision ID: 607cdd2a38bd
Revises: 8f160e537bc2
Create Date: 2026-06-14 14:21:58.972275

google_sub を users から削除し、マルチ IdP 対応の oauth_identities テーブル
(provider, subject の複合 UNIQUE) へ移行する。あわせて users.email を nullable 化し
UNIQUE を外す (Apple の Hide My Email など、メール無し・重複を許容するため)。
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "607cdd2a38bd"
down_revision: str | Sequence[str] | None = "8f160e537bc2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add oauth_identities, drop users.google_sub, and relax users.email."""
    op.create_table(
        "oauth_identities",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "subject", name="uq_provider_subject"),
    )
    op.create_index(op.f("ix_oauth_identities_user_id"), "oauth_identities", ["user_id"], unique=False)
    op.alter_column("users", "email", existing_type=sa.VARCHAR(length=320), nullable=True)
    op.drop_constraint(op.f("users_email_key"), "users", type_="unique")
    op.drop_constraint(op.f("users_google_sub_key"), "users", type_="unique")
    op.drop_column("users", "google_sub")


def downgrade() -> None:
    """Restore users.google_sub / unique email and drop oauth_identities."""
    op.add_column("users", sa.Column("google_sub", sa.VARCHAR(length=255), autoincrement=False, nullable=False))
    op.create_unique_constraint(
        op.f("users_google_sub_key"), "users", ["google_sub"], postgresql_nulls_not_distinct=False
    )
    op.create_unique_constraint(op.f("users_email_key"), "users", ["email"], postgresql_nulls_not_distinct=False)
    op.alter_column("users", "email", existing_type=sa.VARCHAR(length=320), nullable=False)
    op.drop_index(op.f("ix_oauth_identities_user_id"), table_name="oauth_identities")
    op.drop_table("oauth_identities")
