import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from app.stt.pipeline import (
    _to_segments,  # pyright: ignore[reportPrivateUsage]  # noqa: PLC2701
    _wait_for_completion,  # pyright: ignore[reportPrivateUsage]  # noqa: PLC2701
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


def _job_response(status: str, reason: str | None = None) -> dict[str, object]:
    """get_transcription_job のレスポンス相当の dict を組み立てる.

    Args:
        status (str): TranscriptionJobStatus の値 (COMPLETED / FAILED / IN_PROGRESS 等)
        reason (str | None): FAILED 時の FailureReason。None なら含めない。

    Returns:
        dict[str, object]: get_transcription_job のレスポンス相当の dict
    """
    job: dict[str, object] = {"TranscriptionJobStatus": status}
    if reason is not None:
        job["FailureReason"] = reason
    return {"TranscriptionJob": job}


def test_wait_for_completion_returns_when_completed() -> None:
    """ジョブが COMPLETED になったら例外なく終了する."""
    with (
        patch("app.stt.pipeline.asyncio.sleep", new=AsyncMock()),
        patch("app.stt.pipeline.transcribe") as mock_transcribe,
    ):
        mock_transcribe.get_transcription_job.return_value = _job_response("COMPLETED")
        asyncio.run(_wait_for_completion("job-1"))
        mock_transcribe.get_transcription_job.assert_called_once_with(TranscriptionJobName="job-1")


def test_wait_for_completion_raises_on_failed() -> None:
    """ジョブが FAILED になったら理由付きの RuntimeError を送出する."""
    with (
        patch("app.stt.pipeline.asyncio.sleep", new=AsyncMock()),
        patch("app.stt.pipeline.transcribe") as mock_transcribe,
    ):
        mock_transcribe.get_transcription_job.return_value = _job_response("FAILED", reason="bad audio")
        with pytest.raises(RuntimeError, match="bad audio"):
            asyncio.run(_wait_for_completion("job-1"))


def test_wait_for_completion_times_out_after_max_attempts() -> None:
    """ずっと IN_PROGRESS なら max_attempts 回で TimeoutError を送出する."""
    max_attempts = 3
    with (
        patch("app.stt.pipeline.asyncio.sleep", new=AsyncMock()),
        patch("app.stt.pipeline.transcribe") as mock_transcribe,
    ):
        mock_transcribe.get_transcription_job.return_value = _job_response("IN_PROGRESS")
        with pytest.raises(TimeoutError, match="did not complete"):
            asyncio.run(_wait_for_completion("job-1", max_attempts=max_attempts))
        assert mock_transcribe.get_transcription_job.call_count == max_attempts
