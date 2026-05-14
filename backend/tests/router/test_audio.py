from __future__ import annotations

from contextlib import asynccontextmanager
from http import HTTPStatus
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

import app.stt.models as stt_models
from app.llm.summarize.schema import Summary
from main import app

client = TestClient(app)

_VALID_CONTENT_TYPE = "audio/mpeg"
_DUMMY_AUDIO = b"dummy audio content"
_EMPTY_SUMMARY = Summary(overall_summary="test", topics=[], decisions=[], action_items=[])


def test_summarize_audio_returns_summary() -> None:
    mock_models = (MagicMock(), MagicMock())

    @asynccontextmanager
    async def mock_acquire():
        yield mock_models

    with (
        patch.object(stt_models.pool, "acquire", mock_acquire),
        patch("app.router.audio.transcribe_with_diarization", return_value=[]),
        patch("app.router.audio.summarize_chain") as mock_chain,
    ):
        mock_chain.ainvoke = AsyncMock(return_value=_EMPTY_SUMMARY)
        response = client.post(
            "/audio/summarize",
            files={"file": ("test.mp3", _DUMMY_AUDIO, _VALID_CONTENT_TYPE)},
        )

    assert response.status_code == HTTPStatus.OK


def test_summarize_audio_rejects_unsupported_content_type() -> None:
    response = client.post(
        "/audio/summarize",
        files={"file": ("test.txt", _DUMMY_AUDIO, "text/plain")},
    )

    assert response.status_code == HTTPStatus.UNSUPPORTED_MEDIA_TYPE


def test_summarize_audio_rejects_oversized_file() -> None:
    oversized = b"x" * (200 * 1024 * 1024 + 1)

    response = client.post(
        "/audio/summarize",
        files={"file": ("big.mp3", oversized, _VALID_CONTENT_TYPE)},
    )

    assert response.status_code == HTTPStatus.REQUEST_ENTITY_TOO_LARGE
