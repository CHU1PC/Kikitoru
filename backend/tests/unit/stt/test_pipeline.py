from app.stt.pipeline import (
    _to_segments,  # pyright: ignore[reportPrivateUsage]  # noqa: PLC2701
)
from app.stt.schema import Transcript
from app.stt.types import Segment


def _pron(start: str, end: str, content: str) -> dict[str, object]:
    """results.items の pronunciationトークン の dict.

    Args:
        start (str): 開始時間
        end (str): 終了時間
        content (str): 認識結果の文字列

    Returns:
        dict[str, object]: pronunciationトークンの dict
    """
    return {
        "type": "pronunciation",
        "start_time": start,
        "end_time": end,
        "alternatives": [{"content": content}],
    }


def _punct(content: str) -> dict[str, object]:
    """results.items の punctuationトークン の dict.

    Args:
        content (str): 認識結果の文字列

    Returns:
        dict[str, object]: punctuationトークンの dict
    """
    return {
        "type": "punctuation",
        "alternatives": [{"content": content}],
    }


def _make_transcript(items: list[dict[str, object]], speakers: dict[str, str] | None = None) -> Transcript:
    """AWS Transcribe のバッチ結果 JSON の dict を作成する.

    Args:
        items (list[dict[str, object]]): results.items のリスト
        speakers (dict[str, str] | None): results.speaker_labels の dict

    Returns:
        Transcript: AWS Transcribe のバッチ結果 JSON の dict
    """
    results: dict[str, object] = {"items": items}
    if speakers:
        results["speaker_labels"] = {
            "segments": [
                {"items":
                    [
                        {"start_time": start, "speaker_label": label}
                        for start, label in speakers.items()
                    ]
                }
            ]
        }
    return Transcript.model_validate({"results": results})


def test_to_segments_concatenates_words_of_same_speaker() -> None:
    """同じ話者の単語は連結されることを確認する."""
    transcript: Transcript = _make_transcript(
        items=[
            _pron("0.0", "0.5", "Hello"),
            _punct(" "),
            _pron("0.5", "1.0", "world"),
            _punct(".")
        ],
        speakers={"0.0": "spk_0", "0.5": "spk_0"},
    )

    assert _to_segments(transcript) == [
        Segment(start=0.0, end=1.0, speaker_label="Speaker 1", text="Hello world.")
    ]


def test_to_segments_splits_on_speaker_change() -> None:
    """話者交代で分割・ラベルが spk_N -> Speaker N+1."""
    transcript = _make_transcript(
        items=[_pron("0.0", "0.5", "はい"), _pron("1.0", "1.5", "そうですね")],
        speakers={"0.0": "spk_0", "1.0": "spk_1"},
    )
    assert _to_segments(transcript) == [
        Segment(start=0.0, end=0.5, speaker_label="Speaker 1", text="はい"),
        Segment(start=1.0, end=1.5, speaker_label="Speaker 2", text="そうですね"),
    ]


def test_to_segments_same_speaker_returning_creates_separate_segments() -> None:
    """同じ話者が非連続で再登場したら別セグメントになる."""
    transcript = _make_transcript(
        items=[
            _pron("0.0", "0.5", "A1"),
            _pron("1.0", "1.5", "B1"),
            _pron("2.0", "2.5", "A2")
        ],
        speakers={"0.0": "spk_0", "1.0": "spk_1", "2.0": "spk_0"},
    )
    assert _to_segments(transcript) == [
        Segment(start=0.0, end=0.5, speaker_label="Speaker 1", text="A1"),
        Segment(start=1.0, end=1.5, speaker_label="Speaker 2", text="B1"),
        Segment(start=2.0, end=2.5, speaker_label="Speaker 1", text="A2"),
    ]


def test_to_segments_without_speaker_labels_falls_back_to_single_speaker() -> None:
    """分離OFF (speaker_labels 無し) なら全単語が1人 (Speaker 1) にまとまる."""
    transcript = _make_transcript(
        items=[
            _pron("0.0", "0.5", "ひとり"),
            _pron("0.6", "1.0", "ごと")
        ],
        speakers=None,
    )
    assert _to_segments(transcript) == [
        Segment(start=0.0, end=1.0, speaker_label="Speaker 1", text="ひとりごと"),
    ]


def test_to_segments_empty_items_returns_empty() -> None:
    """もし items が空なら空リスト."""
    assert _to_segments(_make_transcript(items=[], speakers=None)) == []
