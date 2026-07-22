import json
from datetime import date

from app.llm.summarize.chain import (
    _format_input,  # ruff:ignore[import-private-name]  # pyright: ignore[reportPrivateUsage]
)
from app.stt.types import Segment

_RECORDED_AT = date(2025, 6, 1)


def test_format_input_empty() -> None:
    """空のセグメント列でも落ちず空配列 [] のJSONを返すことを確認するテスト."""
    result = _format_input(([], _RECORDED_AT))

    assert json.loads(result["segments_json"]) == []


def test_format_input_single_segment() -> None:
    """セグメントが {id, speaker, text} のキー構造でJSON化されることを確認するテスト."""
    segments = [
        Segment(start_ms=0, end_ms=2000, speaker_label="Speaker 0", text="hello"),
    ]

    result = _format_input((segments, _RECORDED_AT))
    payload = json.loads(result["segments_json"])

    assert payload == [{"id": 0, "speaker": "Speaker 0", "text": "hello"}]


def test_format_input_assigns_sequential_ids() -> None:
    """各セグメントに 0 始まりの連番 id が振られることを確認するテスト."""
    segments = [
        Segment(start_ms=0, end_ms=2000, speaker_label="Speaker 0", text="a"),
        Segment(start_ms=2000, end_ms=4000, speaker_label="Speaker 1", text="b"),
        Segment(start_ms=4000, end_ms=6000, speaker_label="Speaker 0", text="c"),
    ]

    result = _format_input((segments, _RECORDED_AT))
    payload = json.loads(result["segments_json"])

    assert [item["id"] for item in payload] == [0, 1, 2]
    assert [item["text"] for item in payload] == ["a", "b", "c"]


def test_format_input_preserves_japanese_characters() -> None:
    """日本語をエスケープせず生の文字のまま出力することを確認するテスト."""
    segments = [
        Segment(start_ms=0, end_ms=2000, speaker_label="Speaker 0", text="こんにちは"),
    ]

    result = _format_input((segments, _RECORDED_AT))

    assert "こんにちは" in result["segments_json"]
    assert "\\u" not in result["segments_json"]


def test_format_input_uses_speaker_label_as_is() -> None:
    """話者ラベルを加工せずそのまま speaker に渡すことを確認するテスト."""
    segments = [
        Segment(start_ms=0, end_ms=2000, speaker_label="田中", text="..."),
    ]

    result = _format_input((segments, _RECORDED_AT))
    payload = json.loads(result["segments_json"])

    assert payload[0]["speaker"] == "田中"


def test_format_input_returns_expected_keys() -> None:
    """プロンプトテンプレートが要求するキーを返すことを確認するテスト."""
    segments = [
        Segment(start_ms=0, end_ms=2000, speaker_label="Speaker 0", text="test"),
    ]

    result = _format_input((segments, _RECORDED_AT))

    assert "segments_json" in result
    assert isinstance(result["segments_json"], str)


def test_format_input_emits_recorded_at_iso() -> None:
    """recorded_at を ISO 8601 形式の日付文字列で渡すことを確認するテスト."""
    result = _format_input(([], _RECORDED_AT))

    assert result["recorded_at"] == "2025-06-01"
