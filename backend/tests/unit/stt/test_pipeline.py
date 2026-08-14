import asyncio
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.stt.pipeline import (
    TranscribeJobFailedError,
    _to_segments,  # pyright: ignore[reportPrivateUsage]  # ruff:ignore[import-private-name]
    _wait_for_completion,  # pyright: ignore[reportPrivateUsage]  # ruff:ignore[import-private-name]
    transcribe_with_diarization,
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
        Segment(start_ms=0, end_ms=1000, speaker_label="Speaker 1", text="Hello world.")
    ]


def test_to_segments_splits_on_speaker_change() -> None:
    """話者交代で分割・ラベルが spk_N -> Speaker N+1."""
    transcript = _make_transcript(
        items=[_pron("0.0", "0.5", "はい"), _pron("1.0", "1.5", "そうですね")],
        speakers={"0.0": "spk_0", "1.0": "spk_1"},
    )
    assert _to_segments(transcript) == [
        Segment(start_ms=0, end_ms=500, speaker_label="Speaker 1", text="はい"),
        Segment(start_ms=1000, end_ms=1500, speaker_label="Speaker 2", text="そうですね"),
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
        Segment(start_ms=0, end_ms=500, speaker_label="Speaker 1", text="A1"),
        Segment(start_ms=1000, end_ms=1500, speaker_label="Speaker 2", text="B1"),
        Segment(start_ms=2000, end_ms=2500, speaker_label="Speaker 1", text="A2"),
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
        Segment(start_ms=0, end_ms=1000, speaker_label="Speaker 1", text="ひとりごと"),
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
    """ジョブが FAILED になったら理由付きの TranscribeJobFailedError を送出する."""
    with (
        patch("app.stt.pipeline.asyncio.sleep", new=AsyncMock()),
        patch("app.stt.pipeline.transcribe") as mock_transcribe,
    ):
        mock_transcribe.get_transcription_job.return_value = _job_response("FAILED", reason="bad audio")
        with pytest.raises(TranscribeJobFailedError, match="bad audio"):
            asyncio.run(_wait_for_completion("job-1"))


def test_wait_for_completion_times_out_after_max_polls() -> None:
    """ずっと IN_PROGRESS なら max_polls 回で TimeoutError を送出する."""
    max_polls = 3
    with (
        patch("app.stt.pipeline.asyncio.sleep", new=AsyncMock()),
        patch("app.stt.pipeline.transcribe") as mock_transcribe,
    ):
        mock_transcribe.get_transcription_job.return_value = _job_response("IN_PROGRESS")
        with pytest.raises(TimeoutError, match="did not complete"):
            asyncio.run(_wait_for_completion("job-1", max_polls=max_polls))
        assert mock_transcribe.get_transcription_job.call_count == max_polls


class _ConflictError(Exception):
    """boto3 client の ConflictException 相当 (patch した client に差し込む)."""


def _completed_transcript_bytes() -> bytes:
    """COMPLETED 時に S3 から読む結果 JSON のバイト列を返す.

    Returns:
        bytes: Transcript としてパースできる JSON のバイト列
    """
    return _make_transcript([_pron("0.0", "1.0", "はい")]).model_dump_json().encode()


def test_transcribe_uses_deterministic_job_name() -> None:
    """ジョブ名と結果キーが job_id から決定的に導出されることを確認するテスト."""
    job_id = uuid4()
    with (
        patch("app.stt.pipeline.asyncio.sleep", new=AsyncMock()),
        patch("app.stt.pipeline.transcribe") as mock_transcribe,
        patch("app.stt.pipeline.get_object_bytes", new=AsyncMock(return_value=_completed_transcript_bytes())),
        patch("app.stt.pipeline.cleanup_transcribe_job", new=AsyncMock()),
    ):
        mock_transcribe.exceptions.ConflictException = _ConflictError
        mock_transcribe.get_transcription_job.return_value = _job_response("COMPLETED")

        asyncio.run(transcribe_with_diarization("uploads/a", job_id=job_id))

        kwargs = mock_transcribe.start_transcription_job.call_args.kwargs
        assert kwargs["TranscriptionJobName"] == f"kikitoru-{job_id}"
        assert kwargs["OutputKey"].endswith(f"kikitoru-{job_id}.json")


def test_transcribe_joins_existing_job_on_conflict() -> None:
    """同名ジョブが既にある場合は ConflictException を飲んで既存ジョブに合流することを確認するテスト."""
    job_id = uuid4()
    with (
        patch("app.stt.pipeline.asyncio.sleep", new=AsyncMock()),
        patch("app.stt.pipeline.transcribe") as mock_transcribe,
        patch("app.stt.pipeline.get_object_bytes", new=AsyncMock(return_value=_completed_transcript_bytes())),
        patch("app.stt.pipeline.cleanup_transcribe_job", new=AsyncMock()),
    ):
        mock_transcribe.exceptions.ConflictException = _ConflictError
        mock_transcribe.start_transcription_job.side_effect = _ConflictError
        mock_transcribe.get_transcription_job.return_value = _job_response("COMPLETED")

        segments = asyncio.run(transcribe_with_diarization("uploads/a", job_id=job_id))

        assert segments  # 既存ジョブのポーリングに進み結果が得られる
        mock_transcribe.get_transcription_job.assert_called_once()


def test_transcribe_cleans_up_when_job_failed() -> None:
    """FAILED の場合は次 attempt が作り直せるようジョブを削除することを確認するテスト."""
    job_id = uuid4()
    cleanup = AsyncMock()
    with (
        patch("app.stt.pipeline.asyncio.sleep", new=AsyncMock()),
        patch("app.stt.pipeline.transcribe") as mock_transcribe,
        patch("app.stt.pipeline.cleanup_transcribe_job", new=cleanup),
    ):
        mock_transcribe.exceptions.ConflictException = _ConflictError
        mock_transcribe.get_transcription_job.return_value = _job_response("FAILED", reason="bad audio")

        with pytest.raises(TranscribeJobFailedError):
            asyncio.run(transcribe_with_diarization("uploads/a", job_id=job_id))

        cleanup.assert_awaited_once_with(job_id)


def test_transcribe_keeps_job_on_timeout() -> None:
    """TIMEOUT の場合はジョブを残し, 次 attempt が実行中ジョブに合流できることを確認するテスト."""
    job_id = uuid4()
    cleanup = AsyncMock()
    with (
        patch("app.stt.pipeline.asyncio.sleep", new=AsyncMock()),
        patch("app.stt.pipeline.transcribe") as mock_transcribe,
        patch("app.stt.pipeline.cleanup_transcribe_job", new=cleanup),
    ):
        mock_transcribe.exceptions.ConflictException = _ConflictError
        mock_transcribe.get_transcription_job.return_value = _job_response("IN_PROGRESS")

        with pytest.raises(TimeoutError):
            asyncio.run(transcribe_with_diarization("uploads/a", job_id=job_id))

        cleanup.assert_not_awaited()
