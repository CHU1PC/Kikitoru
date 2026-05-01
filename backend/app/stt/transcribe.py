from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from app.stt.types import WhisperSegment


def transcribe(audio: Path) -> list[WhisperSegment]:
    """Transcribes the given audio file using OpenAI's Whisper model.

    Args:
        audio (Path): The path to the audio file to be transcribed.

    Returns:
        list[WhisperSegment]: A list of transcribed segments, each containing the start time,
            end time, and transcribed text.
    """
    msg = f"Transcription function is not implemented yet for audio file: {audio}"
    raise NotImplementedError(msg)
