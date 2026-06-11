from __future__ import annotations

from contextlib import asynccontextmanager
from http import HTTPStatus
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

import app.stt.models as stt_models
from app.db.engine import get_session
from app.db.models import Summary as DBSummary
from app.llm.summarize.schema import Summary
from main import app

client = TestClient(app)

_VALID_CONTENT_TYPE = "audio/mpeg"
_DUMMY_AUDIO = b"dummy audio content"
_EMPTY_SUMMARY = Summary(overall_summary="test", topics=[], decisions=[], action_items=[])


def _make_session_mock(existing: object = None) -> AsyncMock:
    session = AsyncMock()
    session.add = MagicMock()
    result = MagicMock()
    result.first.return_value = existing
    result.all.return_value = []
    session.exec.return_value = result
    return session


@pytest.fixture(autouse=True)
def _override_session():
    # Replace the real DB dependency so tests never touch a live database.
    def override_get_session():
        yield _make_session_mock()

    app.dependency_overrides[get_session] = override_get_session
    yield
    app.dependency_overrides.clear()


def test_summarize_audio_returns_summary() -> None:
    mock_models = (MagicMock(), MagicMock())

    @asynccontextmanager
    async def mock_acquire():
        yield mock_models

    with (
        patch.object(stt_models.pool, "acquire", mock_acquire),
        patch("app.router.audio.transcribe_with_diarization", return_value=[]),
        patch("app.router.audio.summarize_chain") as mock_chain,
        patch("app.router.audio._magic_mime") as mock_magic,
    ):
        mock_magic.from_buffer.return_value = _VALID_CONTENT_TYPE
        mock_chain.ainvoke = AsyncMock(return_value=_EMPTY_SUMMARY)
        response = client.post(
            "/audio/summarize",
            files={"file": ("test.mp3", _DUMMY_AUDIO, _VALID_CONTENT_TYPE)},
        )

    assert response.status_code == HTTPStatus.OK


def test_summarize_audio_rejects_unsupported_content_type() -> None:
    # Real libmagic sniffs the bytes (not the client Content-Type) as text/plain.
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


def test_summarize_audio_idempotent_skips_pipeline() -> None:
    # A row with the same content_hash already exists -> return it, skip STT/LLM.
    existing = DBSummary(filename="prev.mp3", content_hash="abc", overall_summary="previous run")

    def override_get_session():
        yield _make_session_mock(existing=existing)

    app.dependency_overrides[get_session] = override_get_session

    @asynccontextmanager
    async def mock_acquire():
        yield (MagicMock(), MagicMock())

    with (
        patch.object(stt_models.pool, "acquire", mock_acquire),
        patch("app.router.audio.transcribe_with_diarization") as mock_transcribe,
        patch("app.router.audio.summarize_chain") as mock_chain,
        patch("app.router.audio._magic_mime") as mock_magic,
    ):
        mock_magic.from_buffer.return_value = _VALID_CONTENT_TYPE
        mock_chain.ainvoke = AsyncMock()
        response = client.post(
            "/audio/summarize",
            files={"file": ("dup.mp3", _DUMMY_AUDIO, _VALID_CONTENT_TYPE)},
        )

    assert response.status_code == HTTPStatus.OK
    body = response.json()
    assert body["filename"] == "prev.mp3"
    assert body["overall_summary"] == "previous run"
    # The idempotent hit must not run the expensive STT / LLM pipeline.
    mock_transcribe.assert_not_called()
    mock_chain.ainvoke.assert_not_called()
