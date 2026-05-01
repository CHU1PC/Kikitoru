from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from app.stt.types import DiarizationTurn


def diarize(audio: Path) -> list[DiarizationTurn]:
    """Performs speaker diarization on the given audio file.

    Args:
        audio (Path): The path to the audio file to be diarized.

    Returns:
        list[DiarizationTurn]: A list of diarization turns, each containing the start time, end time, and speaker label.
    """
    msg = f"Diarization function is not implemented yet for audio file: {audio}"
    raise NotImplementedError(msg)
