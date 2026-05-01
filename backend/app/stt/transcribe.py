from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

from faster_whisper import WhisperModel  # type: ignore[import-untyped]

from app.stt.types import WhisperSegment

_MODEL_ID = "large-v3"


def transcribe(audio: Path) -> list[WhisperSegment]:
    """Transcribes the given audio file using Whisper large-v3.

    Args:
        audio (Path): The path to the audio file to be transcribed.

    Returns:
        list[WhisperSegment]: A list of transcribed segments, each containing the start time,
            end time, and transcribed text.
    """
    model = WhisperModel(_MODEL_ID, device="cuda", compute_type="int8_float16")
    segments, _ = model.transcribe(str(audio), language="ja", vad_filter=True)  # type: ignore[reportUnknownMemberType]
    return [WhisperSegment(start=s.start, end=s.end, text=s.text) for s in segments]
