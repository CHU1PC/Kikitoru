from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from app.stt.transcribe import transcribe
from app.stt.types import WhisperSegment

if TYPE_CHECKING:
    from pathlib import Path


def _mock_segment(start: float, end: float, text: str) -> MagicMock:
    seg = MagicMock()
    seg.start = start
    seg.end = end
    seg.text = text
    return seg


def test_returns_whisper_segments(tmp_path: Path) -> None:
    audio = tmp_path / "audio.wav"
    audio.touch()

    mock_model = MagicMock()
    mock_model.transcribe.return_value = (
        [_mock_segment(0.0, 1.5, "こんにちは"), _mock_segment(1.5, 3.0, "世界")],
        MagicMock(),
    )

    with patch("app.stt.transcribe.WhisperModel", return_value=mock_model):
        result = transcribe(audio)

    assert result == [
        WhisperSegment(start=0.0, end=1.5, text="こんにちは"),
        WhisperSegment(start=1.5, end=3.0, text="世界"),
    ]


def test_loads_large_v3_on_cuda(tmp_path: Path) -> None:
    audio = tmp_path / "audio.wav"
    audio.touch()

    mock_model = MagicMock()
    mock_model.transcribe.return_value = ([], MagicMock())

    with patch("app.stt.transcribe.WhisperModel", return_value=mock_model) as mock_cls:
        transcribe(audio)

    mock_cls.assert_called_once_with(
        "large-v3", device="cuda", compute_type="int8_float16"
    )


def test_transcribes_in_japanese(tmp_path: Path) -> None:
    audio = tmp_path / "audio.wav"
    audio.touch()

    mock_model = MagicMock()
    mock_model.transcribe.return_value = ([], MagicMock())

    with patch("app.stt.transcribe.WhisperModel", return_value=mock_model):
        transcribe(audio)

    mock_model.transcribe.assert_called_once_with(str(audio), language="ja", vad_filter=True)


def test_empty_audio_returns_empty_list(tmp_path: Path) -> None:
    audio = tmp_path / "audio.wav"
    audio.touch()

    mock_model = MagicMock()
    mock_model.transcribe.return_value = ([], MagicMock())

    with patch("app.stt.transcribe.WhisperModel", return_value=mock_model):
        result = transcribe(audio)

    assert result == []
