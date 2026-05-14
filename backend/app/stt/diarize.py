from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from torch import Tensor

from app.stt.models import diarize_pipeline
from app.stt.types import DiarizationTurn


def diarize(waveform: Tensor, sample_rate: int) -> list[DiarizationTurn]:
    """Performs speaker diarization on the given audio waveform.

    Args:
        waveform (torch.Tensor): Audio waveform tensor of shape (channels, samples).
        sample_rate (int): Sample rate of the waveform in Hz.

    Returns:
        list[DiarizationTurn]: A list of diarization turns, each containing the start time, end time, and speaker label.
    """
    diarization: Any = diarize_pipeline({"waveform": waveform, "sample_rate": sample_rate})  # type: ignore[reportUnknownMemberType]

    return [
        DiarizationTurn(start=segment.start, end=segment.end, speaker=label)
        for segment, _, label in diarization.speaker_diarization.itertracks(yield_label=True)  # type: ignore[union-attr]
    ]
