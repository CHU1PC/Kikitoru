from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pyannote.audio import Pipeline  # type: ignore[import-untyped]
    from torch import Tensor

from app.stt.types import DiarizationTurn


def diarize(waveform: Tensor, sample_rate: int, pipeline: Pipeline) -> list[DiarizationTurn]:
    """Performs speaker diarization on the given audio waveform.

    Args:
        waveform (torch.Tensor): Audio waveform tensor of shape (channels, samples).
        sample_rate (int): Sample rate of the waveform in Hz.
        pipeline (Pipeline): pyannote diarization pipeline instance to use.

    Returns:
        list[DiarizationTurn]: A list of diarization turns.
    """
    diarization: Any = pipeline({"waveform": waveform, "sample_rate": sample_rate})  # type: ignore[reportUnknownMemberType]
    return [
        DiarizationTurn(start=segment.start, end=segment.end, speaker=label)
        for segment, _, label in diarization.speaker_diarization.itertracks(yield_label=True)  # type: ignore[union-attr]
    ]
