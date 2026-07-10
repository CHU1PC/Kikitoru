from __future__ import annotations

import asyncio
import hashlib
from datetime import UTC, datetime
from http import HTTPStatus
from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.audio.intake import (
    _MAGIC_SNIFF_BYTES,  # pyright: ignore[reportPrivateUsage]  # noqa: PLC2701
    _MAX_FILENAME_LENGTH,  # pyright: ignore[reportPrivateUsage]  # noqa: PLC2701
    sanitize_filename,
    spool_upload,
)
from app.db.engine import get_db_session
from app.db.models import JobStatus, TranscriptionJob, User, UserStatus
from app.db.models import Summary as DBSummary
from app.dependencies import get_current_user
from main import app

if TYPE_CHECKING:
    from collections.abc import Generator
    from uuid import UUID

    from httpx import Response

client = TestClient(app)

_USER = User(id=uuid4(), email="owner@example.com", name="Owner", status=UserStatus.approved)
_VALID_CONTENT_TYPE = "audio/mpeg"
_DUMMY_AUDIO = b"dummy audio content"


def _make_job(status: JobStatus = JobStatus.pending, *, job_id: UUID | None = None) -> TranscriptionJob:
    """テスト用の TranscriptionJob を作る (media_key は NOT NULL なので必ず与える).

    Returns:
        TranscriptionJob: 指定 status のテスト用ジョブ.
    """
    return TranscriptionJob(
        id=job_id or uuid4(),
        user_id=_USER.id,
        status=status,
        filename="meeting.mp3",
        content_hash="hash",
        media_key="uploads/test",
        num_speakers=2,
    )


def _create_job_echo(_db: object, *, job_id: UUID, **_kwargs: object) -> TranscriptionJob:
    """create_job のモック: 渡された job_id を持つ新規 pending job を返す (実挙動と同じ).

    Returns:
        TranscriptionJob: job_id を id に持つ pending ジョブ.
    """
    return _make_job(job_id=job_id)


def _post_summarize(**data: str) -> Response:
    """/audio/summarize に有効な音声を POST するヘルパ.

    Returns:
        Response: エンドポイントのレスポンス.
    """
    return client.post(
        "/api/v1/audio/summarize",
        files={"file": ("meeting.mp3", _DUMMY_AUDIO, _VALID_CONTENT_TYPE)},
        data=data,
    )


@pytest.fixture(autouse=True)
def override_session() -> None:
    """get_db_session と get_current_user をモックに差し替える pytest フィクスチャ.

    実 DB を使わずテスト用セッションのモックを提供する. 後始末 (dependency_overrides の
    クリア) は router 配下共通の conftest フィクスチャが行う.
    """
    def override_get_session() -> Generator[AsyncMock]:
        db_session = AsyncMock()
        db_session.add = MagicMock()
        yield db_session

    app.dependency_overrides[get_db_session] = override_get_session
    app.dependency_overrides[get_current_user] = lambda: _USER


@pytest.fixture
def enqueue_mocks() -> Generator[SimpleNamespace]:
    """Enqueue エンドポイントの依存 (dedup / S3保存 / job作成 / MIME) を一括モックする.

    既定は「新規アップロード」の happy path (既存要約なし・進行中ジョブなし・pending 作成).
    各テストは返す namespace 経由で必要なモックだけ上書きする.

    Yields:
        SimpleNamespace: find_summary / find_job / persist / create / magic のモック.
    """
    with (
        patch("app.router.audio.find_by_content_hash", new_callable=AsyncMock) as find_summary,
        patch("app.router.audio.find_active_job_by_hash", new_callable=AsyncMock) as find_job,
        patch("app.router.audio.persist_upload", new_callable=AsyncMock) as persist,
        patch("app.router.audio.create_job", new_callable=AsyncMock) as create,
        patch("app.router.audio.delete_object", new_callable=AsyncMock) as delete,
        patch("app.audio.intake._magic_mime") as magic,
    ):
        find_summary.return_value = None
        find_job.return_value = None
        persist.return_value = "uploads/test"
        create.side_effect = _create_job_echo
        magic.from_buffer.return_value = _VALID_CONTENT_TYPE
        yield SimpleNamespace(
            find_summary=find_summary,
            find_job=find_job,
            persist=persist,
            create=create,
            delete=delete,
            magic=magic,
        )


@pytest.mark.usefixtures("enqueue_mocks")
def test_summarize_new_upload_returns_pending_job() -> None:
    """新規アップロードは 202 で pending ジョブを返すことを確認するテスト."""
    response = _post_summarize()

    assert response.status_code == HTTPStatus.ACCEPTED
    body = response.json()
    assert body["status"] == "pending"
    assert body["summary_id"] is None


def test_summarize_cache_hit_returns_completed(enqueue_mocks: SimpleNamespace) -> None:
    """同一内容の要約が既にあれば 202 completed + summary_id を返し、ジョブを作らないことを確認するテスト."""
    existing = DBSummary(user_id=_USER.id, filename="prev.mp3", content_hash="abc", overall_summary="prev")
    enqueue_mocks.find_summary.return_value = existing

    response = _post_summarize()

    assert response.status_code == HTTPStatus.ACCEPTED
    body = response.json()
    assert body["status"] == "completed"
    assert body["summary_id"] == str(existing.id)
    enqueue_mocks.create.assert_not_called()
    enqueue_mocks.persist.assert_not_called()


def test_summarize_active_job_returns_it(enqueue_mocks: SimpleNamespace) -> None:
    """進行中の同一ジョブがあれば、それを返し二重処理しないことを確認するテスト."""
    active = _make_job(JobStatus.processing)
    enqueue_mocks.find_job.return_value = active

    response = _post_summarize()

    assert response.status_code == HTTPStatus.ACCEPTED
    body = response.json()
    assert body["id"] == str(active.id)
    assert body["status"] == "processing"
    enqueue_mocks.create.assert_not_called()


def test_summarize_forwards_num_speakers(enqueue_mocks: SimpleNamespace) -> None:
    """num_speakers が create_job まで届くことを確認するテスト."""
    expected_speakers = 3

    response = _post_summarize(num_speakers=str(expected_speakers))

    assert response.status_code == HTTPStatus.ACCEPTED
    assert enqueue_mocks.create.call_args.kwargs["num_speakers"] == expected_speakers


@pytest.mark.usefixtures("enqueue_mocks")
def test_summarize_rejects_invalid_num_speakers() -> None:
    """num_speakers=0 が 422 で弾かれることを確認するテスト."""
    response = _post_summarize(num_speakers="0")

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


def test_summarize_rejects_unsupported_content_type() -> None:
    """許可されない MIME タイプを 415 で拒否することを確認するテスト."""
    with patch("app.audio.intake._magic_mime") as magic:
        magic.from_buffer.return_value = "text/plain"
        response = client.post(
            "/api/v1/audio/summarize",
            files={"file": ("note.txt", _DUMMY_AUDIO, "text/plain")},
        )

    assert response.status_code == HTTPStatus.UNSUPPORTED_MEDIA_TYPE


def test_summarize_requires_authentication() -> None:
    """未認証のとき 401 を返すことを確認するテスト."""
    app.dependency_overrides.pop(get_current_user, None)

    response = _post_summarize()

    assert response.status_code == HTTPStatus.UNAUTHORIZED


def test_summarize_rejects_unapproved_user() -> None:
    """未承認 (pending) ユーザーは ApprovedUser ゲートで 403 になることを確認するテスト."""
    pending = User(id=uuid4(), email="pending@example.com", name="Pending", status=UserStatus.pending)
    app.dependency_overrides[get_current_user] = lambda: pending

    response = _post_summarize()

    assert response.status_code == HTTPStatus.FORBIDDEN


def test_summarize_rejects_oversized_file(monkeypatch: pytest.MonkeyPatch) -> None:
    """Endpoint の 413 ガード (file.size > MAX_UPLOAD_BYTES) を確認するテスト."""
    monkeypatch.setattr("app.router.audio.MAX_UPLOAD_BYTES", 10)

    response = client.post(
        "/api/v1/audio/summarize",
        files={"file": ("big.mp3", b"x" * 11, _VALID_CONTENT_TYPE)},
    )

    assert response.status_code == HTTPStatus.REQUEST_ENTITY_TOO_LARGE


def test_summarize_trashed_summary_returns_409(enqueue_mocks: SimpleNamespace) -> None:
    """同一内容の要約がゴミ箱にある場合 409 を返し, ジョブを作らないことを確認するテスト."""
    trashed = DBSummary(
        user_id=_USER.id,
        filename="prev.mp3",
        content_hash="abc",
        overall_summary="prev",
        deleted_at=datetime.now(UTC),
    )
    enqueue_mocks.find_summary.return_value = trashed

    response = _post_summarize()

    assert response.status_code == HTTPStatus.CONFLICT
    enqueue_mocks.create.assert_not_called()
    enqueue_mocks.persist.assert_not_called()


def test_summarize_race_loss_deletes_orphan_media(enqueue_mocks: SimpleNamespace) -> None:
    """並行作成に敗北し既存 job が返った場合, アップロード済み media を削除することを確認するテスト."""
    winner = _make_job(JobStatus.processing)  # 別 id (競合の勝者)
    enqueue_mocks.create.side_effect = None
    enqueue_mocks.create.return_value = winner

    response = _post_summarize()

    assert response.status_code == HTTPStatus.ACCEPTED
    assert response.json()["id"] == str(winner.id)
    enqueue_mocks.delete.assert_awaited_once_with("uploads/test")


def test_get_job_returns_owned_job() -> None:
    """GET /jobs/{id} が owner のジョブ状態を返すことを確認するテスト."""
    job = _make_job(JobStatus.processing)

    with patch("app.router.audio.get_owned_job", new_callable=AsyncMock) as get_owned:
        get_owned.return_value = job
        response = client.get(f"/api/v1/audio/jobs/{job.id}")

    assert response.status_code == HTTPStatus.OK
    assert response.json()["id"] == str(job.id)


def test_get_job_not_found() -> None:
    """他ユーザー/存在しないジョブは 404 を返すことを確認するテスト."""
    with patch("app.router.audio.get_owned_job", new_callable=AsyncMock) as get_owned:
        get_owned.return_value = None
        response = client.get(f"/api/v1/audio/jobs/{uuid4()}")

    assert response.status_code == HTTPStatus.NOT_FOUND


def test_list_jobs_returns_active() -> None:
    """GET /jobs が進行中ジョブの一覧を返すことを確認するテスト."""
    jobs = [_make_job(JobStatus.pending), _make_job(JobStatus.processing)]

    with patch("app.router.audio.list_active_jobs", new_callable=AsyncMock) as list_active:
        list_active.return_value = jobs
        response = client.get("/api/v1/audio/jobs")

    assert response.status_code == HTTPStatus.OK
    assert len(response.json()) == len(jobs)


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
        ("が.mp3", "が.mp3"),
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
