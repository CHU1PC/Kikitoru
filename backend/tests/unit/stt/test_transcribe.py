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
    """TranscribeがWhisperの出力を受け取りWhisperSegmentのリストに変換することを確認するテスト."""
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
    """Transcribeがlanguage=ja・vad_filter=True・文脈条件付け無効で呼ばれることを確認するテスト."""
    audio = np.zeros(16000, dtype=np.float32)
    mock_whisper = MagicMock()
    mock_whisper.transcribe.return_value = ([], MagicMock())

    transcribe(audio, mock_whisper)

    mock_whisper.transcribe.assert_called_once_with(
        audio, language="ja", vad_filter=True, condition_on_previous_text=False
    )


def test_empty_audio_returns_empty_list() -> None:
    """Transcribeが文字起こし結果が無いとき空リストを返すことを確認するテスト."""
    audio = np.zeros(16000, dtype=np.float32)
    mock_whisper = MagicMock()
    mock_whisper.transcribe.return_value = ([], MagicMock())

    result = transcribe(audio, mock_whisper)

    assert result == []
