import pytest

from app.settings import Settings


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # 単一値
        ("https://example.com", ["https://example.com"]),
        # カンマ区切り
        ("https://a.com,https://b.com", ["https://a.com", "https://b.com"]),
        # 前後の空白を strip
        ("https://a.com, https://b.com ", ["https://a.com", "https://b.com"]),
        # 空要素を除去
        ("https://a.com,,https://b.com,", ["https://a.com", "https://b.com"]),
        # JSON 配列
        ('["https://a.com","https://b.com"]', ["https://a.com", "https://b.com"]),
        # 前後空白付きの JSON
        ('  ["https://a.com"]  ', ["https://a.com"]),
        # list はそのまま通す
        (["https://a.com", "https://b.com"], ["https://a.com", "https://b.com"]),
    ],
)
def test_parse_allowed_origins(raw: object, expected: list[str]) -> None:
    """ALLOWED_ORIGINS をカンマ区切り/JSON配列/リストから正しく解釈することを確認するテスト."""
    assert Settings._parse_allowed_origins(raw) == expected  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]


def test_parse_allowed_origins_rejects_invalid_json() -> None:
    """[ で始まる不正な JSON を ValueError で弾くことを確認するテスト."""
    with pytest.raises(ValueError, match="invalid"):
        Settings._parse_allowed_origins('["https://a.com"')  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
