from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from app.stt.diarize import diarize
from app.stt.types import DiarizationTurn

if TYPE_CHECKING:
    from pathlib import Path


def _mock_segment(start: float, end: float) -> MagicMock:
    seg = MagicMock()
    seg.start = start
    seg.end = end
    return seg


def test_raises_when_pipeline_is_none(tmp_path: Path) -> None:
    audio = tmp_path / "audio.wav"
    audio.touch()

    with patch("app.stt.diarize.Pipeline") as mock_cls:
        mock_cls.from_pretrained.return_value = None
        with pytest.raises(ValueError, match="Failed to load"):
            diarize(audio)


def test_raises_when_audio_not_found(tmp_path: Path) -> None:
    audio = tmp_path / "missing.wav"

    with patch("app.stt.diarize.Pipeline") as mock_cls:
        mock_cls.from_pretrained.return_value = MagicMock()
        with pytest.raises(ValueError, match="Audio file not found"):
            diarize(audio)


def test_returns_diarization_turns(tmp_path: Path) -> None:
    audio = tmp_path / "audio.wav"
    audio.touch()

    mock_output = MagicMock()
    mock_output.speaker_diarization.itertracks.return_value = [
        (_mock_segment(0.0, 2.5), None, "SPEAKER_00"),
        (_mock_segment(2.5, 5.0), None, "SPEAKER_01"),
    ]

    mock_pipeline = MagicMock()
    mock_pipeline.return_value = mock_output

    with (
        patch("app.stt.diarize.Pipeline") as mock_cls,
        patch("app.stt.diarize.torchaudio.load", return_value=(MagicMock(), 16000)),
    ):
        mock_cls.from_pretrained.return_value = mock_pipeline
        result = diarize(audio)

    assert result == [
        DiarizationTurn(start=0.0, end=2.5, speaker="SPEAKER_00"),
        DiarizationTurn(start=2.5, end=5.0, speaker="SPEAKER_01"),
    ]


def test_loads_model_on_cuda(tmp_path: Path) -> None:
    audio = tmp_path / "audio.wav"
    audio.touch()

    mock_pipeline = MagicMock()
    mock_pipeline.return_value.speaker_diarization.itertracks.return_value = []

    with (
        patch("app.stt.diarize.Pipeline") as mock_cls,
        patch("app.stt.diarize.torch") as mock_torch,
        patch("app.stt.diarize.torchaudio.load", return_value=(MagicMock(), 16000)),
    ):
        mock_cls.from_pretrained.return_value = mock_pipeline
        diarize(audio)

    mock_pipeline.to.assert_called_once_with(mock_torch.device("cuda"))
