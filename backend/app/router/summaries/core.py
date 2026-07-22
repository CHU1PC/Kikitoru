from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from loguru import logger

from app.db.summaries import build_summary_read, get_owned_summary, get_transcript_segments, list_summaries_page
from app.db.summary_group import get_owned_group
from app.dependencies import ApprovedUser, DbSessionDep
from app.schema.summaries import (
    SummaryEdit,
    SummaryListItem,
    SummaryPageResponse,
    SummaryResponse,
    TranscriptSegmentResponse,
)
from app.storage import delete_object

router = APIRouter(tags=["summaries"])


@router.get("")
async def list_summaries_endpoint(
    db_session: DbSessionDep,
    user: ApprovedUser,
    limit: Annotated[int, Query(ge=1, le=100, description="1ページあたりの件数")] = 50,
    offset: Annotated[int, Query(ge=0, description="スキップする件数")] = 0,
    group_id: Annotated[UUID | None, Query(description="検索対象の要約グループのID")] = None,
    *,
    ungrouped_only: Annotated[bool, Query(description="True なら未分類の要約のみを返す")] = False,
) -> SummaryPageResponse:
    """アクティブな要約を作成日時の降順でページ取得する.

    Args:
        db_session (AsyncSession): SQLAlchemy の非同期セッション.
        user (User): 現在のユーザー.
        limit (int): 1ページあたりの件数 (1〜100). default: 50
        offset (int): スキップする件数 (0以上). default: 0
        group_id (UUID | None): 検索対象の要約グループの ID.
        ungrouped_only (bool): True なら未分類の要約のみを返す.

    Returns:
        SummaryPageResponse: ページ内の要約リストと総数・limit・offset.
    """
    items, total = await list_summaries_page(
        db_session,
        user.id,
        deleted=False,
        limit=limit,
        offset=offset,
        group_id=group_id,
        ungrouped_only=ungrouped_only
    )
    return SummaryPageResponse(
        items=[SummaryListItem.model_validate(s) for s in items], total=total, limit=limit, offset=offset
    )


@router.get("/trash")
async def list_deleted_summaries_endpoint(
    db_session: DbSessionDep,
    user: ApprovedUser,
    limit: Annotated[int, Query(ge=1, le=100, description="1ページあたりの件数")] = 50,
    offset: Annotated[int, Query(ge=0, description="スキップする件数")] = 0,
) -> SummaryPageResponse:
    """削除済み (ゴミ箱) の要約を作成日時の降順でページ取得する.

    Args:
        db_session (AsyncSession): SQLAlchemy の非同期セッション.
        user (User): 現在のユーザー.
        limit (int): 1ページあたりの件数 (1〜100). default: 50
        offset (int): スキップする件数 (0以上). default: 0

    Returns:
        SummaryPageResponse: ページ内の削除済み要約リストと総数・limit・offset.
    """
    items, total = await list_summaries_page(db_session, user.id, deleted=True, limit=limit, offset=offset)
    return SummaryPageResponse(
        items=[SummaryListItem.model_validate(s) for s in items], total=total, limit=limit, offset=offset
    )


@router.get("/{summary_id}")
async def get_summary_endpoint(summary_id: UUID, db_session: DbSessionDep, user: ApprovedUser) -> SummaryResponse:
    """一つの要約の詳細を返す. 存在しない/他ユーザー/削除済みは 404.

    Args:
        summary_id (UUID): 要約の ID.
        db_session (AsyncSession): SQLAlchemy の非同期セッション.
        user (User): 現在のユーザー.

    Returns:
        SummaryResponse: 要約の詳細.

    Raises:
        HTTPException: 404 - 要約が見つからない場合.
    """
    summary = await get_owned_summary(db_session, user.id, summary_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="Summary not found")
    return await build_summary_read(db_session, summary)


@router.get("/{summary_id}/transcript")
async def get_transcript_endpoint(
    summary_id: UUID, db_session: DbSessionDep, user: ApprovedUser
) -> list[TranscriptSegmentResponse]:
    """要約の文字起こし(transcript)を時系列順で返す. 見つからない/他ユーザー/削除済みは 404.

    Args:
        summary_id (UUID): 要約の ID.
        db_session (AsyncSession): SQLAlchemy の非同期セッション.
        user (User): 現在のユーザー.

    Returns:
        list[TranscriptSegmentResponse]: 文字起こしセグメントのリスト.

    Raises:
        HTTPException: 404 - 要約が見つからない場合.
    """
    summary = await get_owned_summary(db_session, user.id, summary_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="Summary not found")
    transcript_segments = await get_transcript_segments(db_session, summary_id)
    return [TranscriptSegmentResponse.model_validate(seg) for seg in transcript_segments]


@router.patch("/{summary_id}")
async def update_summary_endpoint(
    summary_id: UUID, edit: SummaryEdit, db_session: DbSessionDep, user: ApprovedUser
) -> SummaryResponse:
    """要約本体 (filename / overall_summary) を部分更新する. 見つからなければ 404.

    Args:
        summary_id (UUID): 要約の ID.
        edit (SummaryEdit): 更新内容.
        db_session (AsyncSession): SQLAlchemy の非同期セッション.
        user (User): 現在のユーザー.

    Returns:
        SummaryResponse: 更新後の要約.

    Raises:
        HTTPException: 404 - 要約が見つからない場合.
    """
    summary = await get_owned_summary(db_session, user.id, summary_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="Summary not found")
    if edit.group_id is not None:
        group = await get_owned_group(db_session, user.id, edit.group_id)
        if group is None:
            raise HTTPException(status_code=404, detail="Group not found")
    if edit.filename is not None:
        summary.filename = edit.filename
    if edit.overall_summary is not None:
        summary.overall_summary = edit.overall_summary
    # group_id が指定された場合のみ更新するために exclude_unset=True で dict に変換
    fields = edit.model_dump(exclude_unset=True)
    if "group_id" in fields:
        summary.group_id = fields["group_id"]
    db_session.add(summary)
    await db_session.commit()
    return await build_summary_read(db_session, summary)


@router.delete("/{summary_id}", status_code=204)
async def delete_summary_endpoint(summary_id: UUID, db_session: DbSessionDep, user: ApprovedUser) -> None:
    """要約をソフト削除する (ゴミ箱へ). 見つからなければ 404.

    Args:
        summary_id (UUID): 要約の ID.
        db_session (AsyncSession): SQLAlchemy の非同期セッション.
        user (User): 現在のユーザー.

    Raises:
        HTTPException: 404 - 要約が見つからない場合.
    """
    summary = await get_owned_summary(db_session, user.id, summary_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="Summary not found")
    summary.deleted_at = datetime.now(UTC)
    db_session.add(summary)
    await db_session.commit()


@router.post("/{summary_id}/restore")
async def restore_summary_endpoint(summary_id: UUID, db_session: DbSessionDep, user: ApprovedUser) -> SummaryResponse:
    """ゴミ箱の要約を復元する. ゴミ箱に無い/見つからない場合は 404.

    Args:
        summary_id (UUID): 要約の ID.
        db_session (AsyncSession): SQLAlchemy の非同期セッション.
        user (User): 現在のユーザー.

    Returns:
        SummaryResponse: 復元後の要約.

    Raises:
        HTTPException: 404 - ゴミ箱に該当の要約が無い場合.
    """
    summary = await get_owned_summary(db_session, user.id, summary_id, include_deleted=True)
    if summary is None or summary.deleted_at is None:
        raise HTTPException(status_code=404, detail="Summary not found")
    summary.deleted_at = None
    db_session.add(summary)
    await db_session.commit()
    return await build_summary_read(db_session, summary)


@router.delete("/{summary_id}/permanent", status_code=204)
async def permanently_delete_summary_endpoint(
    summary_id: UUID, db_session: DbSessionDep, user: ApprovedUser
) -> None:
    """ゴミ箱の要約を完全削除する. ゴミ箱に無い/見つからない場合は 404.

    Args:
        summary_id (UUID): 要約の ID.
        db_session (AsyncSession): SQLAlchemy の非同期セッション.
        user (User): 現在のユーザー.

    Raises:
        HTTPException: 404 - ゴミ箱に該当の要約が無い場合.
    """
    summary = await get_owned_summary(db_session, user.id, summary_id, include_deleted=True)
    if summary is None or summary.deleted_at is None:
        raise HTTPException(status_code=404, detail="Summary not found")
    media_key = summary.media_key  # 行削除前に控える
    await db_session.delete(summary)  # DB にデータがあるのに S3 にメディアが無い場合を避けるために DB 削除は先に行う
    await db_session.commit()
    # DB 削除後にメディアを best-effort で削除 (失敗しても 204。孤児は S3 ライフサイクルで回収)
    if media_key:
        try:
            await delete_object(media_key)
        except Exception as e:  # ruff:ignore[blind-except]
            logger.warning(f"Failed to delete media {media_key}: {e}")
