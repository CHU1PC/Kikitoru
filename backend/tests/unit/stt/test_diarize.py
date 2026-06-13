from __future__ import annotations

from unittest.mock import MagicMock

from app.stt.diarize import diarize
from app.stt.types import DiarizationTurn


def _mock_segment(start: float, end: float) -> MagicMock:
    seg = MagicMock()
    seg.start = start
    seg.end = end
    return seg


def test_returns_diarization_turns() -> None:
    """Diarize が Pipeline の出力を受け取り DiarizationTurn のリストに変換することを確認するテスト."""
    waveform = MagicMock()
    sample_rate = 16000
    mock_output = MagicMock()
    mock_output.speaker_diarization.itertracks.return_value = [
        (_mock_segment(0.0, 2.5), None, "SPEAKER_00"),
        (_mock_segment(2.5, 5.0), None, "SPEAKER_01"),
    ]
    mock_pipeline = MagicMock(return_value=mock_output)

    result = diarize(waveform, sample_rate, mock_pipeline)

    assert result == [
        DiarizationTurn(start=0.0, end=2.5, speaker="SPEAKER_00"),
        DiarizationTurn(start=2.5, end=5.0, speaker="SPEAKER_01"),
    ]


def test_passes_waveform_dict_to_pipeline() -> None:
    """波形とsample_rateをdictにまとめてpipelineに渡すことを確認するテスト."""
    waveform = MagicMock()
    sample_rate = 16000
    mock_pipeline = MagicMock()
    mock_pipeline.return_value.speaker_diarization.itertracks.return_value = []

    diarize(waveform, sample_rate, mock_pipeline)

    mock_pipeline.assert_called_once_with({"waveform": waveform, "sample_rate": sample_rate})


def test_passes_num_speakers_to_pipeline_when_given() -> None:
    """num_speakers を指定したとき pipeline に num_speakers が渡ることを確認するテスト."""
    waveform = MagicMock()
    sample_rate = 16000
    mock_pipeline = MagicMock()
    mock_pipeline.return_value.speaker_diarization.itertracks.return_value = []

    diarize(waveform, sample_rate, mock_pipeline, num_speakers=2)

    mock_pipeline.assert_called_once_with(
        {"waveform": waveform, "sample_rate": sample_rate}, num_speakers=2
    )


def test_empty_audio_returns_empty_list() -> None:
    """話者ターンが無いとき空リストを返すことを確認するテスト."""
    waveform = MagicMock()
    sample_rate = 16000
    mock_pipeline = MagicMock()
    mock_pipeline.return_value.speaker_diarization.itertracks.return_value = []

    result = diarize(waveform, sample_rate, mock_pipeline)

    assert result == []
