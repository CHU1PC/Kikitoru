"""drop procrastinate schema.

Revision ID: f338548ceb94
Revises: 101d6fcdd23a
Create Date: 2026-08-04 21:17:11.305398

"""
import importlib.util
from collections.abc import Sequence
from pathlib import Path
from typing import cast

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f338548ceb94"
down_revision: str | Sequence[str] | None = "101d6fcdd23a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SIBLING = "b45ad4f9f69c_add_procrastinate_schema.py"


def _sibling_sql(name: str) -> str:
    """b45ad4f9f69c が持つ SQL 定数を読み出す (600 行の複製を避けるため).

    Args:
        name (str): 取り出す定数名 ("_UPGRADE_SQL" / "_DOWNGRADE_SQL")

    Returns:
        str: 定数に入っている SQL 文字列

    Raises:
        RuntimeError: revision ファイルを読み込めなかった場合
    """
    path = Path(__file__).with_name(_SIBLING)
    spec = importlib.util.spec_from_file_location("_procrastinate_schema_revision", path)
    if spec is None or spec.loader is None:
        msg = f"cannot load {path}"
        raise RuntimeError(msg)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return cast("str", getattr(module, name))


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(_sibling_sql("_DOWNGRADE_SQL"))


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(_sibling_sql("_UPGRADE_SQL"))
