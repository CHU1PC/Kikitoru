import json
from datetime import date

from app.llm.summarize.chain import _format_input
from app.stt.types import Segment

_RECORDED_AT = date(2025, 6, 1)


def test_format_input_empty():
    result = _format_input(([], _RECORDED_AT))

    assert json.loads(result["segments_json"]) == []


def test_format_input_single_segment():
    segments = [
        Segment(start=0.0, end=2.0, speaker_label="Speaker 0", text="hello"),
    ]

    result = _format_input((segments, _RECORDED_AT))
    payload = json.loads(result["segments_json"])

    assert payload == [{"id": 0, "speaker": "Speaker 0", "text": "hello"}]


def test_format_input_assigns_sequential_ids():
    segments = [
        Segment(start=0.0, end=2.0, speaker_label="Speaker 0", text="a"),
        Segment(start=2.0, end=4.0, speaker_label="Speaker 1", text="b"),
        Segment(start=4.0, end=6.0, speaker_label="Speaker 0", text="c"),
    ]

    result = _format_input((segments, _RECORDED_AT))
    payload = json.loads(result["segments_json"])

    assert [item["id"] for item in payload] == [0, 1, 2]
    assert [item["text"] for item in payload] == ["a", "b", "c"]


def test_format_input_preserves_japanese_characters():
    segments = [
        Segment(start=0.0, end=2.0, speaker_label="Speaker 0", text="こんにちは"),
    ]

    result = _format_input((segments, _RECORDED_AT))

    # ensure_ascii=False means Japanese characters appear literally,
    # not as \uXXXX escape sequences.
    assert "こんにちは" in result["segments_json"]
    assert "\\u" not in result["segments_json"]


def test_format_input_uses_speaker_label_as_is():
    """Speaker label can be normalized ("Speaker 0") or a real name; both pass through."""
    segments = [
        Segment(start=0.0, end=2.0, speaker_label="田中", text="..."),
    ]

    result = _format_input((segments, _RECORDED_AT))
    payload = json.loads(result["segments_json"])

    assert payload[0]["speaker"] == "田中"


def test_format_input_returns_expected_keys():
    """The returned dict matches what the prompt template expects."""
    segments = [
        Segment(start=0.0, end=2.0, speaker_label="Speaker 0", text="test"),
    ]

    result = _format_input((segments, _RECORDED_AT))

    assert "segments_json" in result
    assert isinstance(result["segments_json"], str)


def test_format_input_emits_recorded_at_iso():
    """recorded_at is passed to the prompt as an ISO 8601 date string."""
    result = _format_input(([], _RECORDED_AT))

    assert result["recorded_at"] == "2025-06-01"
