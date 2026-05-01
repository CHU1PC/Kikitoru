import json

from app.llm.summarize.chain import _format_segments  # type: ignore[import]
from app.stt.types import Segment


def test_format_segments_empty():
    result = _format_segments([])

    assert json.loads(result["segments_json"]) == []


def test_format_segments_single_segment():
    segments = [
        Segment(start_seconds=0.0, end_seconds=2.0, speaker_label="Speaker 0", text="hello"),
    ]

    result = _format_segments(segments)
    payload = json.loads(result["segments_json"])

    assert payload == [{"id": 0, "speaker": "Speaker 0", "text": "hello"}]


def test_format_segments_assigns_sequential_ids():
    segments = [
        Segment(start_seconds=0.0, end_seconds=2.0, speaker_label="Speaker 0", text="a"),
        Segment(start_seconds=2.0, end_seconds=4.0, speaker_label="Speaker 1", text="b"),
        Segment(start_seconds=4.0, end_seconds=6.0, speaker_label="Speaker 0", text="c"),
    ]

    result = _format_segments(segments)
    payload = json.loads(result["segments_json"])

    assert [item["id"] for item in payload] == [0, 1, 2]
    assert [item["text"] for item in payload] == ["a", "b", "c"]


def test_format_segments_preserves_japanese_characters():
    segments = [
        Segment(start_seconds=0.0, end_seconds=2.0, speaker_label="Speaker 0", text="こんにちは"),
    ]

    result = _format_segments(segments)

    # ensure_ascii=False means Japanese characters appear literally,
    # not as \uXXXX escape sequences.
    assert "こんにちは" in result["segments_json"]
    assert "\\u" not in result["segments_json"]


def test_format_segments_uses_speaker_label_as_is():
    """Speaker label can be normalized ("Speaker 0") or a real name; both pass through."""
    segments = [
        Segment(start_seconds=0.0, end_seconds=2.0, speaker_label="田中", text="..."),
    ]

    result = _format_segments(segments)
    payload = json.loads(result["segments_json"])

    assert payload[0]["speaker"] == "田中"


def test_format_segments_returns_segments_json_key():
    """The returned dict matches what the prompt template expects."""
    segments = [
        Segment(start_seconds=0.0, end_seconds=2.0, speaker_label="Speaker 0", text="test"),
    ]

    result = _format_segments(segments)

    assert "segments_json" in result
    assert isinstance(result["segments_json"], str)
