from __future__ import annotations

from http import HTTPStatus
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from app.db.engine import get_db_session
from app.db.models import Summary as DBSummary
from app.db.models import TranscriptSegment, User, UserStatus
from app.dependencies import get_current_user
from main import app

if TYPE_CHECKING:
    from collections.abc import Generator

client = TestClient(app)

_USER = User(id=uuid4(), email="owner@example.com", name="Owner", status=UserStatus.approved)

_NEW_ID_AFTER = 2
_NEW_ID_PREPEND = 5
_SPLIT_PARTS = 2
_RENAME_COUNT = 3


def _install_session(db_session: AsyncMock) -> None:
    """指定したセッションモックを get_db_session の override として登録する."""

    def override_get_session() -> Generator[AsyncMock]:
        yield db_session

    app.dependency_overrides[get_db_session] = override_get_session
    app.dependency_overrides[get_current_user] = lambda: _USER


def _summary() -> DBSummary:
    return DBSummary(user_id=_USER.id, filename="m.mp3", overall_summary="o")


def _seg(
    summary_id: UUID,
    *,
    seg_id: int,
    rank: str,
    speaker: str = "spk_0",
    start: int = 0,
    end: int = 500,
    text: str = "hi"
) -> TranscriptSegment:
    return TranscriptSegment(
        id=seg_id, summary_id=summary_id, rank=rank, speaker_label=speaker, start_ms=start, end_ms=end, text=text
    )


def _first(value: object) -> MagicMock:
    result = MagicMock()
    result.first.return_value = value
    return result


def _all(values: list[object]) -> MagicMock:
    result = MagicMock()
    result.all.return_value = values
    return result


def _assign_new_id(new_id: int) -> object:
    def assign(obj: TranscriptSegment) -> None:
        if obj.id is None:
            obj.id = new_id

    return assign


# ---- insert ----------------------------------------------------------------


def test_insert_segment_after_anchor_returns_201() -> None:
    """after_id を指定した挿入が 201 とセグメントを返すことを確認するテスト."""
    summary = _summary()
    anchor = _seg(summary.id, seg_id=1, rank="a0")
    db_session = AsyncMock()
    db_session.add = MagicMock(side_effect=_assign_new_id(2))
    db_session.get.return_value = anchor
    # get_owned_summary (endpoint), get_owned_summary (load_owned_segment), _rank_after
    db_session.exec.side_effect = [_first(summary), _first(summary), _first("a2")]
    _install_session(db_session)

    response = client.post(
        f"/api/v1/summaries/{summary.id}/transcript",
        json={"speaker_label": "田中", "start_ms": 100, "end_ms": 200, "text": "お元気ですか", "after_id": 1},
    )

    assert response.status_code == HTTPStatus.CREATED
    body = response.json()
    assert body["id"] == _NEW_ID_AFTER
    assert (body["speaker_label"], body["start_ms"], body["end_ms"], body["text"]) == ("田中", 100, 200, "お元気ですか")


def test_insert_segment_prepend_returns_201() -> None:
    """after_id=None (先頭挿入) が 201 を返すことを確認するテスト."""
    summary = _summary()
    db_session = AsyncMock()
    db_session.add = MagicMock(side_effect=_assign_new_id(5))
    db_session.exec.side_effect = [_first(summary), _first("a5")]  # get_owned_summary, _rank_after(None)
    _install_session(db_session)

    response = client.post(
        f"/api/v1/summaries/{summary.id}/transcript",
        json={"speaker_label": "田中", "start_ms": 0, "end_ms": 100, "text": "先頭", "after_id": None},
    )

    assert response.status_code == HTTPStatus.CREATED
    assert response.json()["id"] == _NEW_ID_PREPEND


def test_insert_segment_bad_after_id_returns_404() -> None:
    """他人/存在しない after_id が 404 を返すことを確認するテスト."""
    summary = _summary()
    db_session = AsyncMock()
    db_session.get.return_value = None  # load_owned_segment の segment 取得が None
    db_session.exec.side_effect = [_first(summary), _first(summary)]
    _install_session(db_session)

    response = client.post(
        f"/api/v1/summaries/{summary.id}/transcript",
        json={"speaker_label": "x", "start_ms": 0, "end_ms": 100, "text": "t", "after_id": 999},
    )

    assert response.status_code == HTTPStatus.NOT_FOUND


def test_insert_segment_summary_not_found_returns_404() -> None:
    """他人/存在しない要約への挿入が 404 を返すことを確認するテスト."""
    db_session = AsyncMock()
    db_session.exec.return_value = _first(None)
    _install_session(db_session)

    response = client.post(
        f"/api/v1/summaries/{uuid4()}/transcript",
        json={"speaker_label": "x", "start_ms": 0, "end_ms": 100, "text": "t"},
    )

    assert response.status_code == HTTPStatus.NOT_FOUND


def test_insert_segment_end_before_start_returns_422() -> None:
    """end_ms <= start_ms が 422 を返すことを確認するテスト."""
    summary = _summary()
    db_session = AsyncMock()
    db_session.exec.return_value = _first(summary)
    _install_session(db_session)

    response = client.post(
        f"/api/v1/summaries/{summary.id}/transcript",
        json={"speaker_label": "x", "start_ms": 200, "end_ms": 100, "text": "t"},
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


# ---- update ----------------------------------------------------------------


def test_update_segment_returns_200() -> None:
    """自分のセグメントの PATCH が 200 と更新後を返すことを確認するテスト."""
    summary = _summary()
    seg = _seg(summary.id, seg_id=1, rank="a0", text="old")
    db_session = AsyncMock()
    db_session.add = MagicMock()
    db_session.get.return_value = seg
    db_session.exec.return_value = _first(summary)  # load_owned_segment 内の get_owned_summary
    _install_session(db_session)

    response = client.patch(f"/api/v1/summaries/{summary.id}/transcript/1", json={"text": "new"})

    assert response.status_code == HTTPStatus.OK
    assert response.json()["text"] == "new"


def test_update_segment_not_found_returns_404() -> None:
    """存在しないセグメントの PATCH が 404 を返すことを確認するテスト."""
    summary = _summary()
    db_session = AsyncMock()
    db_session.get.return_value = None
    db_session.exec.return_value = _first(summary)
    _install_session(db_session)

    response = client.patch(f"/api/v1/summaries/{summary.id}/transcript/999", json={"text": "x"})

    assert response.status_code == HTTPStatus.NOT_FOUND


def test_update_segment_required_null_returns_422() -> None:
    """必須フィールドに null を送ると 422 を返すことを確認するテスト."""
    summary = _summary()
    seg = _seg(summary.id, seg_id=1, rank="a0")
    db_session = AsyncMock()
    db_session.add = MagicMock()
    db_session.get.return_value = seg
    db_session.exec.return_value = _first(summary)
    _install_session(db_session)

    response = client.patch(f"/api/v1/summaries/{summary.id}/transcript/1", json={"text": None})

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


# ---- delete ----------------------------------------------------------------


def test_delete_segment_returns_204() -> None:
    """自分のセグメントの DELETE が 204 を返すことを確認するテスト."""
    summary = _summary()
    seg = _seg(summary.id, seg_id=1, rank="a0")
    db_session = AsyncMock()
    db_session.get.return_value = seg
    db_session.exec.return_value = _first(summary)
    _install_session(db_session)

    response = client.delete(f"/api/v1/summaries/{summary.id}/transcript/1")

    assert response.status_code == HTTPStatus.NO_CONTENT
    db_session.delete.assert_awaited_once_with(seg)


def test_delete_segment_not_found_returns_404() -> None:
    """存在しないセグメントの DELETE が 404 を返すことを確認するテスト."""
    summary = _summary()
    db_session = AsyncMock()
    db_session.get.return_value = None
    db_session.exec.return_value = _first(summary)
    _install_session(db_session)

    response = client.delete(f"/api/v1/summaries/{summary.id}/transcript/999")

    assert response.status_code == HTTPStatus.NOT_FOUND


# ---- split -----------------------------------------------------------------


def test_split_segment_returns_two_with_speaker_after() -> None:
    """分割が 201 で2件返し、speaker_after が後半に反映されることを確認するテスト."""
    summary = _summary()
    seg = _seg(summary.id, seg_id=1, rank="a0", speaker="spk_0", start=0, end=1000, text="ab")
    db_session = AsyncMock()
    db_session.add = MagicMock(side_effect=_assign_new_id(2))
    db_session.get.return_value = seg
    # load_owned_segment の get_owned_summary, split 内の _rank_after
    db_session.exec.side_effect = [_first(summary), _first(None)]
    _install_session(db_session)

    response = client.post(
        f"/api/v1/summaries/{summary.id}/transcript/1/split",
        json={"at_ms": 400, "text_before": "a", "text_after": "b", "speaker_after": "spk_1"},
    )

    assert response.status_code == HTTPStatus.CREATED
    body = response.json()
    assert len(body) == _SPLIT_PARTS
    assert (body[0]["text"], body[0]["end_ms"], body[0]["speaker_label"]) == ("a", 400, "spk_0")
    assert (body[1]["text"], body[1]["start_ms"], body[1]["speaker_label"]) == ("b", 400, "spk_1")


def test_split_segment_out_of_range_returns_422() -> None:
    """at_ms が範囲外なら 422 を返すことを確認するテスト."""
    summary = _summary()
    seg = _seg(summary.id, seg_id=1, rank="a0", start=0, end=1000)
    db_session = AsyncMock()
    db_session.get.return_value = seg
    db_session.exec.return_value = _first(summary)
    _install_session(db_session)

    response = client.post(
        f"/api/v1/summaries/{summary.id}/transcript/1/split",
        json={"at_ms": 1000, "text_before": "a", "text_after": "b"},
    )

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


# ---- merge -----------------------------------------------------------------


def test_merge_segments_returns_survivor_with_speaker() -> None:
    """結合が 200 で survivor を返し、speaker_label 指定が反映されることを確認するテスト."""
    summary = _summary()
    seg1 = _seg(summary.id, seg_id=1, rank="a0", speaker="spk_0", start=0, end=500, text="A")
    seg2 = _seg(summary.id, seg_id=2, rank="a1", speaker="spk_1", start=500, end=900, text="B")
    db_session = AsyncMock()
    db_session.add = MagicMock()
    db_session.exec.side_effect = [_first(summary), _all([seg1, seg2])]  # get_owned_summary, merge の select
    _install_session(db_session)

    response = client.post(
        f"/api/v1/summaries/{summary.id}/transcript/merge",
        json={"segment_ids": [1, 2], "speaker_label": "田中"},
    )

    assert response.status_code == HTTPStatus.OK
    body = response.json()
    assert body["id"] == 1
    assert (body["text"], body["start_ms"], body["end_ms"], body["speaker_label"]) == ("A B", 0, 900, "田中")


def test_merge_segments_foreign_id_returns_404() -> None:
    """要約に属さない id が混ざると 404 を返すことを確認するテスト."""
    summary = _summary()
    seg1 = _seg(summary.id, seg_id=1, rank="a0")
    db_session = AsyncMock()
    db_session.exec.side_effect = [_first(summary), _all([seg1])]  # 2件要求したが1件しか取れない
    _install_session(db_session)

    response = client.post(
        f"/api/v1/summaries/{summary.id}/transcript/merge",
        json={"segment_ids": [1, 2]},
    )

    assert response.status_code == HTTPStatus.NOT_FOUND


# ---- rename speaker --------------------------------------------------------


def test_rename_speaker_returns_updated_count() -> None:
    """一括改名が 200 と更新件数を返すことを確認するテスト."""
    summary = _summary()
    db_session = AsyncMock()
    result = MagicMock()
    result.rowcount = 3
    db_session.exec.side_effect = [_first(summary), result]  # get_owned_summary, update
    _install_session(db_session)

    response = client.post(
        f"/api/v1/summaries/{summary.id}/transcript/speakers/rename",
        json={"old_label": "spk_0", "new_label": "田中"},
    )

    assert response.status_code == HTTPStatus.OK
    assert response.json()["updated"] == _RENAME_COUNT


def test_rename_speaker_no_match_returns_zero() -> None:
    """一致0件でも 200 で updated=0 を返すことを確認するテスト."""
    summary = _summary()
    db_session = AsyncMock()
    result = MagicMock()
    result.rowcount = 0
    db_session.exec.side_effect = [_first(summary), result]
    _install_session(db_session)

    response = client.post(
        f"/api/v1/summaries/{summary.id}/transcript/speakers/rename",
        json={"old_label": "unknown", "new_label": "x"},
    )

    assert response.status_code == HTTPStatus.OK
    assert response.json()["updated"] == 0


def test_rename_speaker_summary_not_found_returns_404() -> None:
    """他人/存在しない要約への改名が 404 を返すことを確認するテスト."""
    db_session = AsyncMock()
    db_session.exec.return_value = _first(None)
    _install_session(db_session)

    response = client.post(
        f"/api/v1/summaries/{uuid4()}/transcript/speakers/rename",
        json={"old_label": "a", "new_label": "b"},
    )

    assert response.status_code == HTTPStatus.NOT_FOUND


# ---- auth ------------------------------------------------------------------


def test_transcript_edit_requires_authentication() -> None:
    """未認証のとき transcript 編集が 401 を返すことを確認するテスト."""
    _install_session(AsyncMock())
    app.dependency_overrides.pop(get_current_user, None)

    response = client.delete(f"/api/v1/summaries/{uuid4()}/transcript/1")

    assert response.status_code == HTTPStatus.UNAUTHORIZED
