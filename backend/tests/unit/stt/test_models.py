from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

if TYPE_CHECKING:

    from faster_whisper import WhisperModel  # type: ignore[import-untyped]
    from pyannote.audio import Pipeline  # type: ignore[import-untyped]

from app.stt.models import (
    ModelPool,
    _Slot,  # pyright: ignore[reportPrivateUsage]  # noqa: PLC2701
    get_diarize_pipeline,
    get_whisper,
)


def test_get_whisper_creates_large_v3_on_cuda() -> None:
    """get_whisper が large-v3 を CUDA 上で生成することを確認するテスト."""
    mock_model = MagicMock()

    with patch("app.stt.models.WhisperModel", return_value=mock_model) as mock_cls:
        result = get_whisper()

    mock_cls.assert_called_once_with("large-v3", device="cuda", compute_type="int8_float16")
    assert result is mock_model


def test_get_diarize_pipeline_raises_when_none() -> None:
    """Pipeline のロードに失敗したとき ValueError を送出することを確認するテスト."""
    with patch("app.stt.models.Pipeline") as mock_cls:
        mock_cls.from_pretrained.return_value = None
        with pytest.raises(ValueError, match="Failed to load"):
            get_diarize_pipeline()


def test_get_diarize_pipeline_moves_to_cuda() -> None:
    """Diarization pipeline が CUDA に移されることを確認するテスト."""
    mock_pipeline = MagicMock()

    with (
        patch("app.stt.models.Pipeline") as mock_cls,
        patch("app.stt.models.torch") as mock_torch,
    ):
        mock_cls.from_pretrained.return_value = mock_pipeline
        get_diarize_pipeline()

    mock_pipeline.to.assert_called_once_with(mock_torch.device("cuda"))


def test_acquire_reuses_idle_slot() -> None:
    """Slotを取得して返却した後、同じSlotが再利用されることを確認するテスト."""
    async def acquire_twice() -> tuple[tuple[WhisperModel, Pipeline], tuple[WhisperModel, Pipeline], ModelPool]:
        """ModelPoolから2回連続でSlotを取得し、同じインスタンスが返されることを確認するヘルパー関数.

        Returns:
            tuple[tuple[WhisperModel, Pipeline], tuple[WhisperModel, Pipeline], ModelPool]:
                2回のacquireで得られたWhisperModelとPipelineのタプル、および使用したModelPoolインスタンス.
        """
        pool = ModelPool(max_size=1, idle_timeout=300)
        async with pool.acquire() as first:
            pass
        async with pool.acquire() as second:
            pass
        return first, second, pool

    with (
        patch("app.stt.models.get_whisper", side_effect=object) as mock_get_whisper,
        patch("app.stt.models.get_diarize_pipeline", side_effect=object) as mock_get_diarize,
    ):
        first, second, pool = asyncio.run(acquire_twice())

    assert mock_get_whisper.call_count == 1
    assert mock_get_diarize.call_count == 1
    assert first[0] is second[0]
    assert first[1] is second[1]
    assert pool._idle.qsize() == 1  # noqa: SLF001  # type: ignore[reportPrivateUsage]


def test_acquire_releases_permit_when_body_raises() -> None:
    """Slotの使用中に例外が発生しても、プールの状態が健全であることを確認するテスト."""
    pool = ModelPool(max_size=1, idle_timeout=300)

    async def use_pool_and_fail() -> None:
        """ModelPoolを使用して例外を発生させるヘルパー関数.

        Raises:
            ValueError: 常に発生する例外.
        """
        async with pool.acquire():
            msg = "boom"
            raise ValueError(msg)

    with (
        patch("app.stt.models.get_whisper", side_effect=object),
        patch("app.stt.models.get_diarize_pipeline", side_effect=object),
        pytest.raises(ValueError, match="boom"),
    ):
        asyncio.run(use_pool_and_fail())

    assert not pool._capacity.locked()  # noqa: SLF001  # type: ignore[reportPrivateUsage]
    assert pool._idle.qsize() == 0  # noqa: SLF001  # type: ignore[reportPrivateUsage]


def test_acquire_releases_permit_when_model_creation_fails() -> None:
    """モデルの作成に失敗した場合でも、プールの状態が健全であることを確認するテスト."""
    pool = ModelPool(max_size=1, idle_timeout=300)

    async def use_pool() -> None:
        """ModelPoolを使用してモデルの作成に失敗させるヘルパー関数."""
        async with pool.acquire():
            pass

    with (
        patch("app.stt.models.get_whisper", side_effect=RuntimeError("load failed")),
        patch("app.stt.models.get_diarize_pipeline", side_effect=object),
        pytest.raises(RuntimeError, match="load failed")
    ):
        asyncio.run(use_pool())

    assert not pool._capacity.locked()  # noqa: SLF001  # type: ignore[reportPrivateUsage]
    assert pool._idle.qsize() == 0  # noqa: SLF001  # type: ignore[reportPrivateUsage]


def _idle_slot(last_used: float) -> _Slot:
    """指定されたlast_used値を持つSlotを作成するヘルパー関数.

    Args:
        last_used (float): Slotのlast_used属性に設定する値.

    Returns:
        _Slot: last_used属性が指定された値のSlotインスタンス.
    """
    return _Slot(whisper=object(), pipeline=object(), last_used=last_used)  # type: ignore[arg-type]


def test_evict_idle_removes_only_stale_slots() -> None:
    """アイドル状態のSlotのうち、古いもの(stale)だけが削除されることを確認するテスト."""
    pool = ModelPool(max_size=5, idle_timeout=300)
    now = time.monotonic()
    fresh = _idle_slot(now - 50)
    stale = _idle_slot(now - 550)

    pool._idle.put_nowait(fresh)  # noqa: SLF001  # type: ignore[reportPrivateUsage]
    pool._idle.put_nowait(stale)  # noqa: SLF001  # type: ignore[reportPrivateUsage]

    with patch("app.stt.models.torch") as mock_torch:
        mock_torch.cuda.is_available.return_value = False
        asyncio.run(pool._evict_idle())  # noqa: SLF001  # type: ignore[reportPrivateUsage]

    remaining: list[_Slot] = []
    while not pool._idle.empty():  # noqa: SLF001  # type: ignore[reportPrivateUsage]
        remaining.append(pool._idle.get_nowait())  # noqa: SLF001  # type: ignore[reportPrivateUsage]

    assert len(remaining) == 1
    assert remaining[0] is fresh
