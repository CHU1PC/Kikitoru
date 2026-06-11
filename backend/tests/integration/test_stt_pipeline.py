import asyncio
import itertools
from pathlib import Path

import pytest

from app.stt.models import pool
from app.stt.pipeline import transcribe_with_diarization
from app.stt.types import Segment

# A short two-speaker mock interview shipped with the repo.
_AUDIO = Path(__file__).resolve().parents[3] / "data" / "interview.mp3"


async def _run(audio_path: Path) -> list[Segment]:
    # Mirrors app.router.audio._transcribe: open the file as a binary stream,
    # acquire a real (whisper, pipeline) pair, and run the blocking inference
    # off the event loop -- the full STT path minus the LLM summary step.
    with audio_path.open("rb") as audio:
        async with pool.acquire() as (whisper, pipeline):
            return await asyncio.to_thread(transcribe_with_diarization, audio, whisper, pipeline)


@pytest.fixture(scope="module")
def segments() -> list[Segment]:
    """音声を実モデルで処理し、話者ラベル付きセグメントを返す fixture.

    Returns:
        list[Segment]: 話者ラベル付きの文字起こしセグメント.
    """
    # モデルのロードと推論は重いので、1度だけ実行して全 assert で結果を共有する。
    if not _AUDIO.exists():
        pytest.skip(f"audio fixture not found: {_AUDIO}")
    return asyncio.run(_run(_AUDIO))


def test_pipeline_returns_non_empty_segments(segments: list[Segment]) -> None:
    """パイプラインが非空のセグメントのリストを返すことを確認するテスト."""
    assert isinstance(segments, list)
    assert len(segments) > 0


def test_every_item_is_a_segment(segments: list[Segment]) -> None:
    """全要素が Segment 型であることを確認するテスト."""
    assert all(isinstance(s, Segment) for s in segments)


def test_segment_times_are_within_bounds(segments: list[Segment]) -> None:
    """各セグメントの時刻が 0 以上かつ start <= end であることを確認するテスト."""
    assert all(s.start >= 0 and s.end >= s.start for s in segments)


def test_segments_are_ordered_by_start_time(segments: list[Segment]) -> None:
    """セグメントが開始時刻の昇順に並んでいることを確認するテスト."""
    assert all(a.start <= b.start for a, b in itertools.pairwise(segments))


def test_transcription_produced_text(segments: list[Segment]) -> None:
    """文字起こしが何らかのテキストを生成したことを確認するテスト."""
    total_chars = sum(len(s.text.strip()) for s in segments)
    assert total_chars > 0


def test_every_segment_has_a_speaker_label(segments: list[Segment]) -> None:
    """全セグメントが非空の話者ラベルを持つことを確認するテスト."""
    assert all(isinstance(s.speaker_label, str) and s.speaker_label for s in segments)


def test_diarization_assigned_at_least_one_real_speaker(segments: list[Segment]) -> None:
    """話者分離が UNKNOWN 以外の話者を少なくとも1人割り当てたことを確認するテスト."""
    known = {s.speaker_label for s in segments if s.speaker_label != "UNKNOWN"}
    assert len(known) >= 1
