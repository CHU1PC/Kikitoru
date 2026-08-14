"""add user role and status.

Revision ID: 7cab7f45844c
Revises: 607cdd2a38bd
Create Date: 2026-06-27 20:36:22.807351

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7cab7f45844c"
down_revision: str | Sequence[str] | None = "607cdd2a38bd"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    userrole = sa.Enum("user", "admin", name="userrole")
    userstatus = sa.Enum("pending", "approved", "rejected", name="userstatus")
    userrole.create(op.get_bind(), checkfirst=True)
    userstatus.create(op.get_bind(), checkfirst=True)
    op.add_column("users", sa.Column("role", userrole, nullable=False))
    op.add_column("users", sa.Column("status", userstatus, nullable=False))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("users", "status")
    op.drop_column("users", "role")
    sa.Enum(name="userstatus").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="userrole").drop(op.get_bind(), checkfirst=True)
