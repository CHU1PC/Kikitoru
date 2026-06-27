from __future__ import annotations

import asyncio
import hashlib
from datetime import date
from http import HTTPStatus
from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.audio.intake import (
    _MAGIC_SNIFF_BYTES,  # pyright: ignore[reportPrivateUsage]  # noqa: PLC2701
    _MAX_FILENAME_LENGTH,  # pyright: ignore[reportPrivateUsage]  # noqa: PLC2701
    sanitize_filename,
    spool_upload,
)
from app.db.engine import get_db_session
from app.db.models import Summary as DBSummary
from app.db.models import User
from app.db.summaries import (
    _add_children,  # pyright: ignore[reportPrivateUsage]  # noqa: PLC2701
    create_summary,
)
from app.dependencies import get_current_user
from app.llm.summarize.schema import ActionItem, Decision, Summary, Topic
from main import app

if TYPE_CHECKING:
    from collections.abc import Generator

client = TestClient(app)

_USER = User(id=uuid4(), email="owner@example.com", name="Owner")
_VALID_CONTENT_TYPE = "audio/mpeg"
_DUMMY_AUDIO = b"dummy audio content"
_EMPTY_SUMMARY = Summary(overall_summary="test", topics=[], decisions=[], action_items=[])


def _make_session_mock(existing: object = None) -> AsyncMock:
    db_session = AsyncMock()
    db_session.add = MagicMock()
    result = MagicMock()
    result.first.return_value = existing
    result.all.return_value = []
    db_session.exec.return_value = result
    return db_session


@pytest.fixture(autouse=True)
def override_session() -> None:
    """get_db_session をデフォルトのモックに置き換える pytestフィクスチャ.

    これで、テスト中に実際のデータベースセッションを使用せず、テスト用のセッションのモックを提供できるようになる.
    後始末 (dependency_overrides のクリア) は router 配下共通の conftest フィクスチャが行う.
    """
    def override_get_session() -> Generator[AsyncMock]:
        """get_db_sessionのモックで、テスト用のセッションを提供するジェネレーター関数.

        Yields:
            AsyncMock: テスト用のセッションのモックを提供するためのジェネレーター.
        """
        yield _make_session_mock()

    app.dependency_overrides[get_db_session] = override_get_session
    app.dependency_overrides[get_current_user] = lambda: _USER


@pytest.fixture
def audio_pipeline_mocks() -> Generator[SimpleNamespace]:
    """STT/LLM パイプラインを一括モックする pytest フィクスチャ.

    transcribe_with_diarization / summarize_chain / _magic_mime を patch し、既定で MIME は
    有効な音声、transcribe は空セグメント、要約は空の Summary を返す. 各テストは返り値の
    namespace 経由で必要なモック (transcribe / chain / magic) だけ上書きする.

    Yields:
        SimpleNamespace: transcribe / chain / magic のモックを持つ namespace.
    """
    with (
        patch("app.router.audio.transcribe_with_diarization", new_callable=AsyncMock) as transcribe,
        patch("app.router.audio.summarize_chain") as chain,
        patch("app.audio.intake._magic_mime") as magic,
    ):
        transcribe.return_value = []
        magic.from_buffer.return_value = _VALID_CONTENT_TYPE
        chain.ainvoke = AsyncMock(return_value=_EMPTY_SUMMARY)
        yield SimpleNamespace(transcribe=transcribe, chain=chain, magic=magic)


@pytest.mark.usefixtures("audio_pipeline_mocks")
def test_summarize_audio_returns_summary() -> None:
    """音声ファイルをPOSTして要約が返ることを確認するテスト."""
    response = client.post(
        "/api/v1/audio/summarize",
        files={"file": ("test.mp3", _DUMMY_AUDIO, _VALID_CONTENT_TYPE)},
    )

    assert response.status_code == HTTPStatus.OK


def test_summarize_audio_requires_authentication() -> None:
    """未認証のとき /audio/summarize が 401 を返すことを確認するテスト."""
    app.dependency_overrides.pop(get_current_user, None)

    response = client.post(
        "/api/v1/audio/summarize",
        files={"file": ("test.mp3", _DUMMY_AUDIO, _VALID_CONTENT_TYPE)},
    )

    assert response.status_code == HTTPStatus.UNAUTHORIZED


def test_summarize_audio_forwards_num_speakers(audio_pipeline_mocks: SimpleNamespace) -> None:
    """num_speakers を渡すと transcribe_with_diarization まで届くことを確認するテスト."""
    expected_speakers = 2

    response = client.post(
        "/api/v1/audio/summarize",
        files={"file": ("test.mp3", _DUMMY_AUDIO, _VALID_CONTENT_TYPE)},
        data={"num_speakers": str(expected_speakers)},
    )

    assert response.status_code == HTTPStatus.OK
    # transcribe_with_diarization(spooled, num_speakers) の末尾引数
    assert audio_pipeline_mocks.transcribe.call_args.args[-1] == expected_speakers


def test_summarize_audio_rejects_invalid_num_speakers() -> None:
    """num_speakers=0 が 422 Unprocessable Entity で弾かれることを確認するテスト."""
    response = client.post(
        "/api/v1/audio/summarize",
        files={"file": ("test.mp3", _DUMMY_AUDIO, _VALID_CONTENT_TYPE)},
        data={"num_speakers": "0"},
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


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


def test_summarize_audio_idempotent_skips_pipeline(audio_pipeline_mocks: SimpleNamespace) -> None:
    """要約がidempotentであることを確認するテスト. 既存の要約がある場合、STT/LLMパイプラインをスキップすること."""
    existing = DBSummary(user_id=uuid4(), filename="prev.mp3", content_hash="abc", overall_summary="previous run")

    def override_get_session() -> Generator[AsyncMock]:
        """get_db_sessionのモックで、既存のDBSummaryを返すセッションを提供するジェネレーター関数.

        Yields:
            AsyncMock: 既存のDBSummaryを返すセッションのモック.
        """
        yield _make_session_mock(existing=existing)

    app.dependency_overrides[get_db_session] = override_get_session

    response = client.post(
        "/api/v1/audio/summarize",
        files={"file": ("dup.mp3", _DUMMY_AUDIO, _VALID_CONTENT_TYPE)},
    )

    assert response.status_code == HTTPStatus.OK
    body = response.json()
    assert body["filename"] == "prev.mp3"
    assert body["overall_summary"] == "previous run"
    # 既存の要約がある場合、STT/LLMパイプラインは実行されないことを確認するため、モックの呼び出し回数を検証する.
    audio_pipeline_mocks.transcribe.assert_not_called()
    audio_pipeline_mocks.chain.ainvoke.assert_not_called()


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
        ("が.mp3", "が.mp3"),
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
    assert sanitize_filename(raw) == expected


def test_sanitize_filename_keeps_name_at_max_length() -> None:
    """ファイル名が最大長ちょうどの場合、サニタイズ後も同じ名前であることのテスト."""
    name = "a" * _MAX_FILENAME_LENGTH
    assert sanitize_filename(name) == name


def test_sanitize_filename_trims_name_exceeding_max_length() -> None:
    """ファイル名が最大長を超える場合、サニタイズ後に適切に切り詰められることのテスト."""
    raw = "a" * (_MAX_FILENAME_LENGTH + 50) + ".mp3"
    expected = "a" * (_MAX_FILENAME_LENGTH - len(".mp3")) + ".mp3"
    result = sanitize_filename(raw)
    assert len(result) == _MAX_FILENAME_LENGTH
    assert result.endswith(".mp3")
    assert result == expected


def test_sanitize_filename_trims_name_without_extension() -> None:
    """ファイル名が拡張子なしで最大長を超える場合、サニタイズ後に適切に切り詰められることのテスト."""
    raw = "a" * (_MAX_FILENAME_LENGTH + 50)
    expected = "a" * _MAX_FILENAME_LENGTH
    result = sanitize_filename(raw)
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

    with patch("app.audio.intake._magic_mime") as mock_magic:
        mock_magic.from_buffer.return_value = "audio/mpeg"
        spooled, digest, mime = asyncio.run(spool_upload(file))

    assert digest == hashlib.sha256(content).hexdigest()
    assert mime == "audio/mpeg"
    assert spooled.read() == content
    spooled.close()


def test_spool_upload_sniffs_only_the_head() -> None:
    """MIME 判定が先頭 _MAGIC_SNIFF_BYTES バイトだけで行われることを確認するテスト."""
    file = _mock_upload(b"A" * _MAGIC_SNIFF_BYTES + b"B" * 5000)

    with patch("app.audio.intake._magic_mime") as mock_magic:
        mock_magic.from_buffer.return_value = "audio/wav"
        spooled, _, _ = asyncio.run(spool_upload(file))

    spooled.close()
    mock_magic.from_buffer.assert_called_once_with(b"A" * _MAGIC_SNIFF_BYTES)


def test_spool_upload_rejects_oversized() -> None:
    """累積サイズが上限を超えたら 413 を送出することを確認するテスト."""
    file = _mock_upload(b"x" * 100)

    with (
        patch("app.audio.intake.MAX_UPLOAD_BYTES", 50),
        patch("app.audio.intake._magic_mime"),
        pytest.raises(HTTPException) as exc,
    ):
        asyncio.run(spool_upload(file))

    assert exc.value.status_code == HTTPStatus.REQUEST_ENTITY_TOO_LARGE


def test_spool_upload_handles_empty_file() -> None:
    """空ファイルでも落ちず、空のハッシュと空 head での MIME 判定を行うことを確認するテスト."""
    file = _mock_upload()

    with patch("app.audio.intake._magic_mime") as mock_magic:
        mock_magic.from_buffer.return_value = "application/x-empty"
        spooled, digest, _ = asyncio.run(spool_upload(file))

    spooled.close()
    assert digest == hashlib.sha256(b"").hexdigest()
    mock_magic.from_buffer.assert_called_once_with(b"")


def test_create_summary_returns_existing_on_content_hash_race() -> None:
    """Commit 時に content_hash が重複したら rollback して既存の要約を返すことを確認するテスト."""
    existing = DBSummary(user_id=uuid4(), filename="prev.mp3", content_hash="abc", overall_summary="previous run")
    db_session = _make_session_mock(existing=existing)
    db_session.flush = AsyncMock(side_effect=IntegrityError("stmt", None, Exception("duplicate")))
    data = Summary(overall_summary="new run", topics=[], decisions=[], action_items=[])

    result = asyncio.run(create_summary(db_session, _USER.id, "new.mp3", "abc", data))

    assert result.filename == "prev.mp3"
    assert result.overall_summary == "previous run"
    db_session.rollback.assert_awaited_once()


def test_create_summary_reraises_unrelated_integrity_error() -> None:
    """Content_hash 重複以外の IntegrityError は握りつぶさず再送出することを確認するテスト."""
    db_session = _make_session_mock(existing=None)
    db_session.flush = AsyncMock(side_effect=IntegrityError("stmt", None, Exception("not a dup")))
    data = Summary(overall_summary="new", topics=[], decisions=[], action_items=[])

    with pytest.raises(IntegrityError):
        asyncio.run(create_summary(db_session, _USER.id, "x.mp3", "hash", data))

    db_session.rollback.assert_awaited_once()


def test_add_children_stages_topics_decisions_and_action_items() -> None:
    """topics/decisions/action_items が summary_id 付きで db_session に add されることを確認するテスト."""
    summary_id = uuid4()
    data = Summary(
        overall_summary="o",
        topics=[Topic(title="T1", summary="s1", segment_ids=[0])],
        decisions=[Decision(description="D1", decided_by="alice", segment_ids=[1])],
        action_items=[ActionItem(description="A1", assignee="bob", due_date=date(2025, 6, 1), segment_ids=[2])],
    )
    db_session = MagicMock()

    _add_children(db_session, summary_id, data)

    added = [call.args[0] for call in db_session.add.call_args_list]
    assert len(added) == len(data.topics) + len(data.decisions) + len(data.action_items)
    topic, decision, action = added
    assert topic.summary_id == summary_id
    assert topic.title == "T1"
    assert decision.decided_by == "alice"
    assert action.due_date == date(2025, 6, 1)
