from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.stt.models import get_diarize_pipeline, get_whisper


def test_get_whisper_creates_large_v3_on_cuda() -> None:
    mock_model = MagicMock()

    with patch("app.stt.models.WhisperModel", return_value=mock_model) as mock_cls:
        result = get_whisper()

    mock_cls.assert_called_once_with("large-v3", device="cuda", compute_type="int8_float16")
    assert result is mock_model


def test_get_diarize_pipeline_raises_when_none() -> None:
    with patch("app.stt.models.Pipeline") as mock_cls:
        mock_cls.from_pretrained.return_value = None
        with pytest.raises(ValueError, match="Failed to load"):
            get_diarize_pipeline()


def test_get_diarize_pipeline_moves_to_cuda() -> None:
    mock_pipeline = MagicMock()

    with (
        patch("app.stt.models.Pipeline") as mock_cls,
        patch("app.stt.models.torch") as mock_torch,
    ):
        mock_cls.from_pretrained.return_value = mock_pipeline
        get_diarize_pipeline()

    mock_pipeline.to.assert_called_once_with(mock_torch.device("cuda"))
