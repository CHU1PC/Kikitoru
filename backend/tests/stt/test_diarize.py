from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.stt.diarize import diarize
from app.stt.types import DiarizationTurn


def _mock_segment(start: float, end: float) -> MagicMock:
    seg = MagicMock()
    seg.start = start
    seg.end = end
    return seg


def test_returns_diarization_turns() -> None:
    waveform = MagicMock()
    sample_rate = 16000

    mock_output = MagicMock()
    mock_output.speaker_diarization.itertracks.return_value = [
        (_mock_segment(0.0, 2.5), None, "SPEAKER_00"),
        (_mock_segment(2.5, 5.0), None, "SPEAKER_01"),
    ]

    mock_pipeline = MagicMock(return_value=mock_output)

    with patch("app.stt.diarize.diarize_pipeline", mock_pipeline):
        result = diarize(waveform, sample_rate)

    assert result == [
        DiarizationTurn(start=0.0, end=2.5, speaker="SPEAKER_00"),
        DiarizationTurn(start=2.5, end=5.0, speaker="SPEAKER_01"),
    ]


def test_passes_waveform_dict_to_pipeline() -> None:
    waveform = MagicMock()
    sample_rate = 16000

    mock_pipeline = MagicMock()
    mock_pipeline.return_value.speaker_diarization.itertracks.return_value = []

    with patch("app.stt.diarize.diarize_pipeline", mock_pipeline):
        diarize(waveform, sample_rate)

    mock_pipeline.assert_called_once_with({"waveform": waveform, "sample_rate": sample_rate})


def test_empty_audio_returns_empty_list() -> None:
    waveform = MagicMock()
    sample_rate = 16000

    mock_pipeline = MagicMock()
    mock_pipeline.return_value.speaker_diarization.itertracks.return_value = []

    with patch("app.stt.diarize.diarize_pipeline", mock_pipeline):
        result = diarize(waveform, sample_rate)

    assert result == []
