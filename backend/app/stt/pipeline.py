from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from app.stt.types import Segment

from app.stt.align import align
from app.stt.diarize import diarize
from app.stt.transcribe import transcribe


def transcribe_with_diarization(audio: Path) -> list[Segment]:
    """Transcribes the given audio file and performs speaker diarization, returning aligned segments.

    Args:
        audio (Path): The path to the audio file to be processed.

    Returns:
        list[Segment]: A list of aligned segments. Each segment contains the start
            time, end time, speaker label, and transcribed text.
    """
    if not audio.exists():
        msg = f"Audio file not found: {audio}"
        raise FileNotFoundError(msg)

    transcript = transcribe(audio)
    diarization_turns = diarize(audio)

    return align(transcript, diarization_turns)
