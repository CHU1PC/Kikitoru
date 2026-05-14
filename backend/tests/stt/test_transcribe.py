from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np

from app.stt.transcribe import transcribe
from app.stt.types import WhisperSegment


def _mock_segment(start: float, end: float, text: str) -> MagicMock:
    seg = MagicMock()
    seg.start = start
    seg.end = end
    seg.text = text
    return seg


def test_returns_whisper_segments() -> None:
    audio = np.zeros(16000, dtype=np.float32)
    mock_whisper = MagicMock()
    mock_whisper.transcribe.return_value = (
        [_mock_segment(0.0, 1.5, "こんにちは"), _mock_segment(1.5, 3.0, "世界")],
        MagicMock(),
    )

    result = transcribe(audio, mock_whisper)

    assert result == [
        WhisperSegment(start=0.0, end=1.5, text="こんにちは"),
        WhisperSegment(start=1.5, end=3.0, text="世界"),
    ]


def test_transcribes_in_japanese() -> None:
    audio = np.zeros(16000, dtype=np.float32)
    mock_whisper = MagicMock()
    mock_whisper.transcribe.return_value = ([], MagicMock())

    transcribe(audio, mock_whisper)

    mock_whisper.transcribe.assert_called_once_with(audio, language="ja", vad_filter=True)


def test_empty_audio_returns_empty_list() -> None:
    audio = np.zeros(16000, dtype=np.float32)
    mock_whisper = MagicMock()
    mock_whisper.transcribe.return_value = ([], MagicMock())

    result = transcribe(audio, mock_whisper)

    assert result == []
