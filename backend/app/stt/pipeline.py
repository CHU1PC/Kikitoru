from __future__ import annotations

from typing import IO, TYPE_CHECKING

import numpy as np
import torchaudio  # type: ignore[import-untyped]

if TYPE_CHECKING:
    from faster_whisper import WhisperModel  # type: ignore[import-untyped]
    from pyannote.audio import Pipeline  # type: ignore[import-untyped]

    from app.stt.types import Segment

from app.stt.align import align
from app.stt.diarize import diarize
from app.stt.transcribe import transcribe

_WHISPER_SAMPLE_RATE = 16000


def transcribe_with_diarization(
    audio: IO[bytes],
    whisper: WhisperModel,
    pipeline: Pipeline,
) -> list[Segment]:
    """Transcribes the given audio and performs speaker diarization, returning aligned segments.

    Args:
        audio (IO[bytes]): Audio data as a binary file-like object (e.g. io.BytesIO
            or tempfile.SpooledTemporaryFile).
        whisper (WhisperModel): Whisper model instance to use for transcription.
        pipeline (Pipeline): pyannote diarization pipeline instance to use.

    Returns:
        list[Segment]: A list of aligned segments with speaker labels and transcribed text.
    """
    waveform, sample_rate = torchaudio.load(audio)  # type: ignore[reportUnknownMemberType]

    if sample_rate != _WHISPER_SAMPLE_RATE:
        waveform = torchaudio.functional.resample(waveform, sample_rate, _WHISPER_SAMPLE_RATE)  # type: ignore[reportUnknownMemberType]
        sample_rate = _WHISPER_SAMPLE_RATE

    audio_np: np.ndarray = waveform.mean(dim=0).numpy().astype(np.float32)  # type: ignore[reportUnknownMemberType]

    transcript = transcribe(audio_np, whisper)
    diarization_turns = diarize(waveform, sample_rate, pipeline)

    return align(transcript, diarization_turns)
