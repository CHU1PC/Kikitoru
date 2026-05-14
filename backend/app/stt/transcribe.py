from __future__ import annotations

import numpy as np

from app.stt.models import whisper
from app.stt.types import WhisperSegment

type AudioArray = np.ndarray


def transcribe(audio: AudioArray) -> list[WhisperSegment]:
    """Transcribes the given audio using Whisper large-v3.

    Args:
        audio (AudioArray): Pre-loaded mono 16kHz float32 numpy array.

    Returns:
        list[WhisperSegment]: A list of transcribed segments, each containing the start time,
            end time, and transcribed text.
    """
    segments, _ = whisper.transcribe(audio, language="ja", vad_filter=True)  # type: ignore[reportUnknownMemberType]
    return [WhisperSegment(start=s.start, end=s.end, text=s.text) for s in segments]
