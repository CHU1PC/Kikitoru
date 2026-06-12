from __future__ import annotations

import asyncio
import hashlib
from contextlib import asynccontextmanager
from datetime import date
from http import HTTPStatus
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

import app.stt.models as stt_models
from app.db.engine import get_session
from app.db.models import Summary as DBSummary
from app.llm.summarize.schema import ActionItem, Decision, Summary, Topic
from app.router.audio import (
    _MAGIC_SNIFF_BYTES,  # pyright: ignore[reportPrivateUsage]  # noqa: PLC2701
    _MAX_FILENAME_LENGTH,  # pyright: ignore[reportPrivateUsage]  # noqa: PLC2701
    _add_children,  # pyright: ignore[reportPrivateUsage]  # noqa: PLC2701
    _create_summary,  # pyright: ignore[reportPrivateUsage]  # noqa: PLC2701
    _sanitize_filename,  # pyright: ignore[reportPrivateUsage]  # noqa: PLC2701
    _spool_upload,  # pyright: ignore[reportPrivateUsage]  # noqa: PLC2701
)
from main import app

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Generator

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
def override_session() -> Generator[None]:
    """get_sessionをモックに置き換えるpytestフィクスチャ.

    これで、テスト中に実際のデータベースセッションを使用せず、テスト用のセッションのモックを提供できるようになる.
    """
    def override_get_session() -> Generator[AsyncMock]:
        """get_sessionのモックで、テスト用のセッションを提供するジェネレーター関数.

        Yields:
            None: テスト用のセッションのモックを提供するためのジェネレーター.
        """
        yield _make_session_mock()

    app.dependency_overrides[get_session] = override_get_session
    yield
    app.dependency_overrides.clear()


def test_summarize_audio_returns_summary() -> None:
    """音声ファイルをPOSTして要約が返ることを確認するテスト."""

    @asynccontextmanager
    async def mock_acquire() -> AsyncGenerator[tuple[MagicMock, MagicMock]]:
        """ModelPool.acquire()のモックで、テスト用のWhisperModelとPipelineのタプルを返すコンテキストマネージャー.

        Yields:
            tuple[MagicMock, MagicMock]: テスト用のWhisperModelとPipelineのタプル.
        """
        yield (MagicMock(), MagicMock())

    with (
        patch.object(stt_models.pool, "acquire", mock_acquire),
        patch("app.router.audio.transcribe_with_diarization", return_value=[]),
        patch("app.router.audio.summarize_chain") as mock_chain,
        patch("app.router.audio._magic_mime") as mock_magic,
    ):
        mock_magic.from_buffer.return_value = _VALID_CONTENT_TYPE
        mock_chain.ainvoke = AsyncMock(return_value=_EMPTY_SUMMARY)
        response = client.post(
            "/api/v1/audio/summarize",
            files={"file": ("test.mp3", _DUMMY_AUDIO, _VALID_CONTENT_TYPE)},
        )

    assert response.status_code == HTTPStatus.OK


def test_summarize_audio_rejects_unsupported_content_type() -> None:
    """サポートされていないコンテンツタイプをHTTP 415 Unsupported Media Typeで拒否することを確認するテスト."""
    response = client.post(
        "/api/v1/audio/summarize",
        files={"file": ("test.txt", _DUMMY_AUDIO, "text/plain")},
    )

    assert response.status_code == HTTPStatus.UNSUPPORTED_MEDIA_TYPE


def test_summarize_audio_rejects_oversized_file() -> None:
    """サイズが大きすぎるファイルをHTTP 413 Request Entity Too Largeで拒否することを確認するテスト."""
    oversized = b"x" * (200 * 1024 * 1024 + 1)

    response = client.post(
        "/api/v1/audio/summarize",
        files={"file": ("big.mp3", oversized, _VALID_CONTENT_TYPE)},
    )

    assert response.status_code == HTTPStatus.REQUEST_ENTITY_TOO_LARGE


def test_summarize_audio_idempotent_skips_pipeline() -> None:
    """要約がidempotentであることを確認するテスト. 既存の要約がある場合、STT/LLMパイプラインをスキップすること."""
    existing = DBSummary(filename="prev.mp3", content_hash="abc", overall_summary="previous run")

    def override_get_session() -> Generator[AsyncMock]:
        """get_sessionのモックで、既存のDBSummaryを返すセッションを提供するジェネレーター関数.

        Yields:
            AsyncMock: 既存のDBSummaryを返すセッションのモック.
        """
        yield _make_session_mock(existing=existing)

    app.dependency_overrides[get_session] = override_get_session

    @asynccontextmanager
    async def mock_acquire() -> AsyncGenerator[tuple[MagicMock, MagicMock]]:
        """ModelPool.acquire()のモックで、テスト用のWhisperModelとPipelineのタプルを返すコンテキストマネージャー.

        Yields:
            tuple[MagicMock, MagicMock]: テスト用のWhisperModelとPipelineのタプル.
        """
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
            "/api/v1/audio/summarize",
            files={"file": ("dup.mp3", _DUMMY_AUDIO, _VALID_CONTENT_TYPE)},
        )

    assert response.status_code == HTTPStatus.OK
    body = response.json()
    assert body["filename"] == "prev.mp3"
    assert body["overall_summary"] == "previous run"
    # 既存の要約がある場合、STT/LLMパイプラインは実行されないことを確認するため、モックの呼び出し回数を検証する.
    mock_transcribe.assert_not_called()
    mock_chain.ainvoke.assert_not_called()


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # 空・無効 → "unknown"
        (None, "unknown"),
        ("", "unknown"),
        ("\x00\x01", "unknown"),
        ("   ", "unknown"),
        # 通常・正規化
        ("meeting.mp3", "meeting.mp3"),
        ("  meeting.mp3  ", "meeting.mp3"),
        ("a\x00b.mp3", "ab.mp3"),
        ("\u304b\u3099.mp3", "\u304c.mp3"),
        # パス成分の除去(パストラバーサル対策)
        ("../../etc/passwd", "passwd"),
        ("/abs/path/audio.wav", "audio.wav"),
    ],
)
def test_sanitize_filename(raw: str | None, expected: str) -> None:
    """ファイル名のサニタイズ処理のテスト.

    Args:
        raw (str | None): サニタイズ前のファイル名
        expected (str): サニタイズ後の期待されるファイル名
    """
    assert _sanitize_filename(raw) == expected


def test_sanitize_filename_keeps_name_at_max_length() -> None:
    """ファイル名が最大長ちょうどの場合、サニタイズ後も同じ名前であることのテスト."""
    name = "a" * _MAX_FILENAME_LENGTH
    assert _sanitize_filename(name) == name


def test_sanitize_filename_trims_name_exceeding_max_length() -> None:
    """ファイル名が最大長を超える場合、サニタイズ後に適切に切り詰められることのテスト."""
    raw = "a" * (_MAX_FILENAME_LENGTH + 50) + ".mp3"
    expected = "a" * (_MAX_FILENAME_LENGTH - len(".mp3")) + ".mp3"
    result = _sanitize_filename(raw)
    assert len(result) == _MAX_FILENAME_LENGTH
    assert result.endswith(".mp3")
    assert result == expected


def test_sanitize_filename_trims_name_without_extension() -> None:
    """ファイル名が拡張子なしで最大長を超える場合、サニタイズ後に適切に切り詰められることのテスト."""
    raw = "a" * (_MAX_FILENAME_LENGTH + 50)
    expected = "a" * _MAX_FILENAME_LENGTH
    result = _sanitize_filename(raw)
    assert len(result) == _MAX_FILENAME_LENGTH
    assert result == expected


def _mock_upload(*chunks: bytes) -> MagicMock:
    """ファイルのチャンクを受け取り、AsyncMockでread()がそれらのチャンクを順に返すUploadFileのモックを作成する関数.

    Args:
        *chunks (bytes): ファイルの内容を表す複数のバイト

    Returns:
        MagicMock: read()が指定されたチャンクを順に返すUploadFileのモック.
    """
    file = MagicMock()
    file.read = AsyncMock(side_effect=[*chunks, b""])
    return file


def test_spool_upload_hashes_and_stores_content() -> None:
    """複数チャンクを連結した内容の SHA-256 が一致し、spooled に全内容が入ることを確認するテスト."""
    chunks = [b"part1-", b"part2-", b"part3"]
    content = b"".join(chunks)
    file = _mock_upload(*chunks)

    with patch("app.router.audio._magic_mime") as mock_magic:
        mock_magic.from_buffer.return_value = "audio/mpeg"
        spooled, digest, mime = asyncio.run(_spool_upload(file))

    assert digest == hashlib.sha256(content).hexdigest()
    assert mime == "audio/mpeg"
    assert spooled.read() == content
    spooled.close()


def test_spool_upload_sniffs_only_the_head() -> None:
    """MIME 判定が先頭 _MAGIC_SNIFF_BYTES バイトだけで行われることを確認するテスト."""
    file = _mock_upload(b"A" * _MAGIC_SNIFF_BYTES + b"B" * 5000)

    with patch("app.router.audio._magic_mime") as mock_magic:
        mock_magic.from_buffer.return_value = "audio/wav"
        spooled, _, _ = asyncio.run(_spool_upload(file))

    spooled.close()
    mock_magic.from_buffer.assert_called_once_with(b"A" * _MAGIC_SNIFF_BYTES)


def test_spool_upload_rejects_oversized() -> None:
    """累積サイズが上限を超えたら 413 を送出することを確認するテスト."""
    file = _mock_upload(b"x" * 100)

    with (
        patch("app.router.audio._MAX_UPLOAD_BYTES", 50),
        patch("app.router.audio._magic_mime"),
        pytest.raises(HTTPException) as exc,
    ):
        asyncio.run(_spool_upload(file))

    assert exc.value.status_code == HTTPStatus.REQUEST_ENTITY_TOO_LARGE


def test_spool_upload_handles_empty_file() -> None:
    """空ファイルでも落ちず、空のハッシュと空 head での MIME 判定を行うことを確認するテスト."""
    file = _mock_upload()

    with patch("app.router.audio._magic_mime") as mock_magic:
        mock_magic.from_buffer.return_value = "application/x-empty"
        spooled, digest, _ = asyncio.run(_spool_upload(file))

    spooled.close()
    assert digest == hashlib.sha256(b"").hexdigest()
    mock_magic.from_buffer.assert_called_once_with(b"")


def test_create_summary_returns_existing_on_content_hash_race() -> None:
    """Commit 時に content_hash が重複したら rollback して既存の要約を返すことを確認するテスト."""
    existing = DBSummary(filename="prev.mp3", content_hash="abc", overall_summary="previous run")
    session = _make_session_mock(existing=existing)
    session.flush = AsyncMock(side_effect=IntegrityError("stmt", None, Exception("duplicate")))
    data = Summary(overall_summary="new run", topics=[], decisions=[], action_items=[])

    result = asyncio.run(_create_summary(session, "new.mp3", "abc", data))

    assert result.filename == "prev.mp3"
    assert result.overall_summary == "previous run"
    session.rollback.assert_awaited_once()


def test_create_summary_reraises_unrelated_integrity_error() -> None:
    """Content_hash 重複以外の IntegrityError は握りつぶさず再送出することを確認するテスト."""
    session = _make_session_mock(existing=None)
    session.flush = AsyncMock(side_effect=IntegrityError("stmt", None, Exception("not a dup")))
    data = Summary(overall_summary="new", topics=[], decisions=[], action_items=[])

    with pytest.raises(IntegrityError):
        asyncio.run(_create_summary(session, "x.mp3", "hash", data))

    session.rollback.assert_awaited_once()


def test_add_children_stages_topics_decisions_and_action_items() -> None:
    """topics/decisions/action_items が summary_id 付きで session に add されることを確認するテスト."""
    summary_id = uuid4()
    data = Summary(
        overall_summary="o",
        topics=[Topic(title="T1", summary="s1", segment_ids=[0])],
        decisions=[Decision(description="D1", decided_by="alice", segment_ids=[1])],
        action_items=[ActionItem(description="A1", assignee="bob", due_date=date(2025, 6, 1), segment_ids=[2])],
    )
    session = MagicMock()

    _add_children(session, summary_id, data)

    added = [call.args[0] for call in session.add.call_args_list]
    assert len(added) == len(data.topics) + len(data.decisions) + len(data.action_items)
    topic, decision, action = added
    assert topic.summary_id == summary_id
    assert topic.title == "T1"
    assert decision.decided_by == "alice"
    assert action.due_date == date(2025, 6, 1)
