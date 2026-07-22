from datetime import UTC, date, datetime

import pytest

from app.llm.summarize.schema import ActionItem


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # None はそのまま
        (None, None),
        # date はそのまま通す
        (date(2025, 6, 1), date(2025, 6, 1)),
        # datetime は日付部分だけ取り出す
        (datetime(2025, 6, 1, 12, 0, tzinfo=UTC), date(2025, 6, 1)),
        # ISO 8601 の日付文字列
        ("2025-06-01", date(2025, 6, 1)),
        # ISO 8601 の日時文字列 → 日付部分
        ("2025-06-01T12:00:00", date(2025, 6, 1)),
        # 解釈できない文字列 → None
        ("not a date", None),
        # 非 ISO 形式 → None
        ("06/01/2025", None),
        # 想定外の型 → None
        (12345, None),
    ],
)
def test_parse_due_date(raw: object, expected: date | None) -> None:
    """due_date を date/datetime/ISO文字列から解釈し、解釈不能なら None にすることを確認するテスト."""
    assert ActionItem._parse_due_date(raw) == expected  # ruff:ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]
