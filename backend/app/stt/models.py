from __future__ import annotations

import torch
from faster_whisper import WhisperModel  # type: ignore[import-untyped]
from pyannote.audio import Pipeline  # type: ignore[import-untyped]

from app.settings.config import settings

_WHISPER_MODEL_ID = "large-v3"
_DIARIZATION_MODEL_ID = "pyannote/speaker-diarization-3.1"


def get_whisper() -> WhisperModel:
    """Returns the cached Whisper model, loading it on first call."""
    return WhisperModel(_WHISPER_MODEL_ID, device="cuda", compute_type="int8_float16")


def get_diarize_pipeline() -> Pipeline:
    """Returns the cached pyannote pipeline, loading it on first call.

    Raises:
        ValueError: If the pipeline fails to load from HuggingFace.
    """
    diarize_pipeline = Pipeline.from_pretrained(  # type: ignore[reportUnknownMemberType]
        _DIARIZATION_MODEL_ID,
        token=settings.HF_TOKEN,
    )
    if diarize_pipeline is None:
        msg = "Failed to load the " + _DIARIZATION_MODEL_ID + " pipeline."
        raise ValueError(msg)
    diarize_pipeline.to(torch.device("cuda"))  # type: ignore[reportUnknownMemberType]
    return diarize_pipeline


whisper = get_whisper()
diarize_pipeline = get_diarize_pipeline()
