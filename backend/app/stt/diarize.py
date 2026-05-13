from __future__ import annotations

from typing import TYPE_CHECKING, Any

import torch
import torchaudio  # type: ignore[import-untyped]
from pyannote.audio import Pipeline  # type: ignore[import-untyped]

if TYPE_CHECKING:
    from pathlib import Path

from app.settings.config import settings
from app.stt.types import DiarizationTurn


def diarize(audio: Path) -> list[DiarizationTurn]:
    """Performs speaker diarization on the given audio file.

    Args:
        audio (Path): The path to the audio file to be diarized.

    Returns:
        list[DiarizationTurn]: A list of diarization turns, each containing the start time, end time, and speaker label.

    Raises:
        ValueError: If the Hugging Face token is not set, if the pipeline fails to load, or if the audio file is None
    """
    token = settings.HF_TOKEN

    pipeline = Pipeline.from_pretrained(  # type: ignore[reportUnknownMemberType]
        "pyannote/speaker-diarization-3.1",
        token=token,
    )
    if pipeline is None:
        msg = "Failed to load the pyannote/speaker-diarization-3.1 pipeline."
        raise ValueError(msg)
    pipeline.to(torch.device("cuda"))  # type: ignore[reportUnknownMemberType]

    if not audio.is_file():
        msg = f"Audio file not found: {audio}"
        raise ValueError(msg)
    waveform, sample_rate = torchaudio.load(str(audio))  # type: ignore[reportUnknownMemberType]
    diarization: Any = pipeline({"waveform": waveform, "sample_rate": sample_rate})  # type: ignore[reportUnknownMemberType]

    return [
        DiarizationTurn(start=segment.start, end=segment.end, speaker=label)
        for segment, _, label in diarization.speaker_diarization.itertracks(yield_label=True)  # type: ignore[union-attr]
    ]
