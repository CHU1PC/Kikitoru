from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from app.stt.types import WhisperSegment

if TYPE_CHECKING:
    from faster_whisper import WhisperModel  # type: ignore[import-untyped]

type AudioArray = np.ndarray


def transcribe(audio: AudioArray, whisper: WhisperModel) -> list[WhisperSegment]:
    """Transcribes the given audio using Whisper large-v3.

    Args:
        audio (AudioArray): Pre-loaded mono 16kHz float32 numpy array.
        whisper (WhisperModel): Whisper model instance to use for transcription.

    Returns:
        list[WhisperSegment]: A list of transcribed segments.
    """
    segments, _ = whisper.transcribe(audio, language="ja", vad_filter=True)  # type: ignore[reportUnknownMemberType]
    return [WhisperSegment(start=s.start, end=s.end, text=s.text) for s in segments]
