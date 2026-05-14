from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

import torch
from faster_whisper import WhisperModel  # type: ignore[import-untyped]
from pyannote.audio import Pipeline  # type: ignore[import-untyped]

from app.settings.config import settings

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

_WHISPER_MODEL_ID = "large-v3"
_DIARIZATION_MODEL_ID = "pyannote/speaker-diarization-3.1"


def get_whisper() -> WhisperModel:
    """Load and return a new Whisper model instance.

    Returns:
        WhisperModel: A new Whisper model instance.
    """
    return WhisperModel(_WHISPER_MODEL_ID, device="cuda", compute_type="int8_float16")


def get_diarize_pipeline() -> Pipeline:
    """Get the pyannote speaker diarization pipeline loaded from HuggingFace.

    Returns:
        Pipeline: A new pyannote diarization pipeline instance.

    Raises:
        ValueError: If the pipeline fails to load from HuggingFace.
    """
    pipeline = Pipeline.from_pretrained(  # type: ignore[reportUnknownMemberType]
        _DIARIZATION_MODEL_ID,
        token=settings.HF_TOKEN,
    )
    if pipeline is None:
        msg = "Failed to load the " + _DIARIZATION_MODEL_ID + " pipeline."
        raise ValueError(msg)
    pipeline.to(torch.device("cuda"))  # type: ignore[reportUnknownMemberType]
    return pipeline


class ModelPool:
    """On-demand pool of (WhisperModel, Pipeline) pairs up to a configurable maximum."""

    def __init__(self, max_size: int) -> None:
        """Initialize the pool.

        Args:
            max_size (int): Maximum number of concurrent model pairs.
        """
        self._pool: asyncio.Queue[tuple[WhisperModel, Pipeline]] = asyncio.Queue()
        self._lock = asyncio.Lock()
        self._current = 0
        self._max = max_size

    @asynccontextmanager
    async def acquire(self) -> AsyncGenerator[tuple[WhisperModel, Pipeline]]:
        """Acquire a model pair, creating one on demand if under the limit.

        Yields:
            tuple[WhisperModel, Pipeline]: A pair of model instances for inference.
        """
        try:
            slot = self._pool.get_nowait()
        except asyncio.QueueEmpty:
            async with self._lock:
                if self._current < self._max:
                    self._current += 1
                    should_create = True
                else:
                    should_create = False

            if should_create:
                slot = await asyncio.to_thread(lambda: (get_whisper(), get_diarize_pipeline()))
            else:
                slot = await self._pool.get()

        try:
            yield slot
        finally:
            self._pool.put_nowait(slot)


pool = ModelPool(settings.STT_POOL_SIZE)
