from uuid import UUID

from fastapi import APIRouter, HTTPException

from app.db.summaries import get_owned_summary
from app.db.transcript_edits import (
    delete_segment,
    insert_segment,
    load_owned_segment,
    merge_segments,
    rename_speaker,
    split_segment,
    update_segment,
)
from app.dependencies import ApprovedUser, DbSessionDep
from app.schema.summaries import (
    SpeakerRename,
    SpeakerRenameResult,
    TranscriptSegmentCreate,
    TranscriptSegmentEdit,
    TranscriptSegmentMerge,
    TranscriptSegmentResponse,
    TranscriptSegmentSplit,
)

router = APIRouter(tags=["summaries"])


@router.post("/{summary_id}/transcript", status_code=201)
async def insert_segment_endpoint(
    summary_id: UUID, body: TranscriptSegmentCreate, db_session: DbSessionDep, user: ApprovedUser
) -> TranscriptSegmentResponse:
    """抜けた transcript segment を挿入する.

    Args:
        summary_id (UUID): 親 summary の ID
        body (TranscriptSegmentCreate): 挿入する transcript segment の情報
        db_session (DbSessionDep): データベースセッション
        user (ApprovedUser): 承認済みユーザー

    Returns:
        TranscriptSegmentResponse: 挿入された transcript segment の情報

    Raises:
        HTTPException: 404 - 親 summary が見つからない場合、またはユーザーが所有していない場合
        HTTPException: 422 - 挿入する位置が不正な場合
    """
    summary = await get_owned_summary(db_session, user.id, summary_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="Summary not found or not owned by user")
    anchor = None
    if body.after_id is not None:
        anchor = await load_owned_segment(db_session, user.id, summary_id, body.after_id)
        if anchor is None:
            raise HTTPException(status_code=404, detail="Anchor segment not found or not owned by user")
    try:
        segment = await insert_segment(db_session, summary_id, body, anchor)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return TranscriptSegmentResponse.model_validate(segment)


@router.post("/{summary_id}/transcript/merge")
async def merge_segments_endpoint(
    summary_id: UUID, body: TranscriptSegmentMerge, db_session: DbSessionDep, user: ApprovedUser
) -> TranscriptSegmentResponse:
    """複数の transcript segment を1つに結合する.

    Args:
        summary_id (UUID): 親 summary の ID
        body (TranscriptSegmentMerge): 結合する transcript segment の情報
        db_session (DbSessionDep): データベースセッション
        user (ApprovedUser): 承認済みユーザー

    Returns:
        TranscriptSegmentResponse: 結合された transcript segment の情報

    Raises:
        HTTPException: 404 - 親 summary が見つからない場合、またはユーザーが所有していない場合
        HTTPException: 422 - 結合するセグメントが不正な場合
    """
    summary = await get_owned_summary(db_session, user.id, summary_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="Summary not found or not owned by user")
    survivor = await merge_segments(db_session, summary_id, body.segment_ids, body.speaker_label)
    if survivor is None:
        raise HTTPException(status_code=404, detail="Segments to merge are invalid or not owned by user")
    return TranscriptSegmentResponse.model_validate(survivor)


@router.post("/{summary_id}/transcript/speakers/rename")
async def rename_speaker_endpoint(
    summary_id: UUID, body: SpeakerRename, db_session: DbSessionDep, user: ApprovedUser
) -> SpeakerRenameResult:
    """話者ラベルを変更する.

    Args:
        summary_id (UUID): 親 summary の ID
        body (SpeakerRename): 変更する話者ラベルの情報
        db_session (DbSessionDep): データベースセッション
        user (ApprovedUser): 承認済みユーザー

    Returns:
        SpeakerRenameResult: 変更された話者ラベルの情報

    Raises:
        HTTPException: 404 - 親 summary が見つからない場合、またはユーザーが所有していない場合
    """
    summary = await get_owned_summary(db_session, user.id, summary_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="Summary not found or not owned by user")
    updated = await rename_speaker(db_session, summary_id, body.old_label, body.new_label)
    return SpeakerRenameResult(updated=updated)


@router.post("/{summary_id}/transcript/{segment_id}/split", status_code=201)
async def split_segment_endpoint(
    summary_id: UUID, segment_id: int, body: TranscriptSegmentSplit, db_session: DbSessionDep, user: ApprovedUser
) -> list[TranscriptSegmentResponse]:
    """セグメントを2つに分割する.

    Args:
        summary_id (UUID): 親 summary の ID
        segment_id (int): 分割する transcript segment の ID
        body (TranscriptSegmentSplit): 分割する位置と分割後のテキスト
        db_session (DbSessionDep): データベースセッション
        user (ApprovedUser): 承認済みユーザー

    Returns:
        list[TranscriptSegmentResponse]: 分割後の2つの transcript segment の情報

    Raises:
        HTTPException: 404 - 親 summary が見つからない, ユーザーが所有していない, 分割対象のセグメントが見つからない場合
        HTTPException: 422 - 分割位置が範囲外の場合
    """
    segment = await load_owned_segment(db_session, user.id, summary_id, segment_id)
    if segment is None:
        raise HTTPException(status_code=404, detail="Segment not found")
    try:
        segments = await split_segment(db_session, segment, body)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return [TranscriptSegmentResponse.model_validate(s) for s in segments]


@router.patch("/{summary_id}/transcript/{segment_id}")
async def update_segment_endpoint(
    summary_id: UUID, segment_id: int, body: TranscriptSegmentEdit, db_session: DbSessionDep, user: ApprovedUser
) -> TranscriptSegmentResponse:
    """Segment を部分更新する. 無ければ 404, 必須 null/end_ms<=start_ms は 422.

    Args:
        summary_id (UUID): 親 summary の ID
        segment_id (int): 更新する transcript segment の ID
        body (TranscriptSegmentEdit): 更新する transcript segment の情報
        db_session (DbSessionDep): データベースセッション
        user (ApprovedUser): 承認済みユーザー

    Returns:
        TranscriptSegmentResponse: 更新後の transcript segment の情報

    Raises:
        HTTPException: 404 - 親 summary が見つからない, ユーザーが所有していない, 更新対象のセグメントが見つからない場合
        HTTPException: 422 - 更新内容が不正な場合
    """
    segment = await load_owned_segment(db_session, user.id, summary_id, segment_id)
    if segment is None:
        raise HTTPException(status_code=404, detail="Segment not found")
    try:
        updated = await update_segment(db_session, segment, body)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return TranscriptSegmentResponse.model_validate(updated)


@router.delete("/{summary_id}/transcript/{segment_id}", status_code=204)
async def delete_segment_endpoint(
    summary_id: UUID, segment_id: int, db_session: DbSessionDep, user: ApprovedUser
) -> None:
    """Segment を削除する. 無ければ 404.

    Args:
        summary_id (UUID): 親 summary の ID
        segment_id (int): 削除する transcript segment の ID
        db_session (DbSessionDep): データベースセッション
        user (ApprovedUser): 承認済みユーザー

    Raises:
        HTTPException: 404 - 親 summary が見つからない, ユーザーが所有していない, 削除対象のセグメントが見つからない場合
    """
    segment = await load_owned_segment(db_session, user.id, summary_id, segment_id)
    if segment is None:
        raise HTTPException(status_code=404, detail="Segment not found")
    await delete_segment(db_session, segment)
