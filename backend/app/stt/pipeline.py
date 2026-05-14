from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import torchaudio  # type: ignore[import-untyped]

if TYPE_CHECKING:
    from pathlib import Path

    from app.stt.types import Segment

from app.stt.align import align
from app.stt.diarize import diarize
from app.stt.transcribe import transcribe

_WHISPER_SAMPLE_RATE = 16000


def transcribe_with_diarization(audio: Path) -> list[Segment]:
    """Transcribes the given audio file and performs speaker diarization, returning aligned segments.

    Args:
        audio (Path): The path to the audio file to be processed.

    Returns:
        list[Segment]: A list of aligned segments. Each segment contains the start
            time, end time, speaker label, and transcribed text.

    Raises:
        FileNotFoundError: If the audio file does not exist.
    """
    if not audio.exists():
        msg = f"Audio file not found: {audio}"
        raise FileNotFoundError(msg)

    waveform, sample_rate = torchaudio.load(str(audio))  # type: ignore[reportUnknownMemberType]

    if sample_rate != _WHISPER_SAMPLE_RATE:
        waveform = torchaudio.functional.resample(waveform, sample_rate, _WHISPER_SAMPLE_RATE)  # type: ignore[reportUnknownMemberType]
        sample_rate = _WHISPER_SAMPLE_RATE

    audio_np: np.ndarray = waveform.mean(dim=0).numpy().astype(np.float32)  # type: ignore[reportUnknownMemberType]

    transcript = transcribe(audio_np)
    diarization_turns = diarize(waveform, sample_rate)

    return align(transcript, diarization_turns)
