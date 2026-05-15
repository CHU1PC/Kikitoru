from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import torch
from faster_whisper import WhisperModel  # type: ignore[import-untyped]
from pyannote.audio import Pipeline  # type: ignore[import-untyped]

from app.settings.config import settings

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

_WHISPER_MODEL_ID = "large-v3"
_DIARIZATION_MODEL_ID = "pyannote/speaker-diarization-3.1"
_CLEANUP_INTERVAL_SECONDS = 60


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

    # pyannote は from_pretrained 内部で TF32 を無効化する。速度優先のため再有効化。
    # 精度は微減するが、Ampere+ GPU の matmul/conv が大幅に高速化される。
    torch.backends.cuda.matmul.allow_tf32 = True
    torch.backends.cudnn.allow_tf32 = True

    return pipeline


@dataclass
class _Slot:
    whisper: WhisperModel
    pipeline: Pipeline
    last_used: float = field(default_factory=time.monotonic)


class ModelPool:
    """On-demand pool of (WhisperModel, Pipeline) pairs up to a configurable maximum."""

    def __init__(self, max_size: int, idle_timeout: float) -> None:
        """Initialize the pool.

        Args:
            max_size (int): Maximum number of concurrent model pairs.
            idle_timeout (float): Seconds before an idle slot is unloaded.
        """
        self._pool: asyncio.Queue[_Slot] = asyncio.Queue()
        self._lock = asyncio.Lock()
        self._current = 0
        self._max = max_size
        self._idle_timeout = idle_timeout
        self._cleanup_task: asyncio.Task[None] | None = None

    def _ensure_cleanup_running(self) -> None:
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def _cleanup_loop(self) -> None:
        while True:
            await asyncio.sleep(_CLEANUP_INTERVAL_SECONDS)
            await self._evict_idle()

    async def _evict_idle(self) -> None:
        now = time.monotonic()
        keep: list[_Slot] = []
        while True:
            try:
                slot = self._pool.get_nowait()
                if now - slot.last_used < self._idle_timeout:
                    keep.append(slot)
                else:
                    async with self._lock:
                        self._current -= 1
            except asyncio.QueueEmpty:
                break
        for slot in keep:
            self._pool.put_nowait(slot)

    @asynccontextmanager
    async def acquire(self) -> AsyncGenerator[tuple[WhisperModel, Pipeline]]:
        """Acquire a model pair, creating one on demand if under the limit.

        Yields:
            tuple[WhisperModel, Pipeline]: A pair of model instances for inference.
        """
        self._ensure_cleanup_running()

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
                whisper, pipeline = await asyncio.to_thread(
                    lambda: (get_whisper(), get_diarize_pipeline())
                )
                slot = _Slot(whisper=whisper, pipeline=pipeline)
            else:
                slot = await self._pool.get()

        try:
            yield slot.whisper, slot.pipeline
        finally:
            slot.last_used = time.monotonic()
            self._pool.put_nowait(slot)


pool = ModelPool(settings.STT_POOL_SIZE, settings.STT_IDLE_TIMEOUT_SECONDS)
