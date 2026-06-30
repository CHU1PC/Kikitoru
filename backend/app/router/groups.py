from uuid import UUID

from fastapi import APIRouter, HTTPException
from sqlalchemy.exc import IntegrityError

from app.db.models import SummaryGroup
from app.db.summary_group import (
    create_group,
    delete_group,
    get_owned_group,
    list_groups,
    rename_group,
)
from app.dependencies import ApprovedUser, DbSessionDep
from app.schema.summaries import (
    SummaryGroupCreate,
    SummaryGroupEdit,
    SummaryGroupResponse,
)

router = APIRouter(prefix="/groups", tags=["groups"])


@router.post("", status_code=201)
async def create_group_endpoint(
    body: SummaryGroupCreate, db_session: DbSessionDep, user: ApprovedUser
) -> SummaryGroupResponse:
    """要約グループを作成する.

    Args:
        body (SummaryGroupCreate): 作成する要約グループの情報.
        db_session (AsyncSession): SQLAlchemy の非同期セッション.
        user (User): 現在のユーザー.

    Returns:
        SummaryGroupResponse: 作成された要約グループの情報.

    Raises:
        HTTPException: 同じ名前の要約グループが既に存在する場合
    """
    group = SummaryGroup(user_id=user.id, name=body.name)
    try:
        created_group = await create_group(db_session, group)
    except IntegrityError as exc:
        await db_session.rollback()
        raise HTTPException(status_code=400, detail="同じ名前の要約グループが既に存在します") from exc
    return SummaryGroupResponse.model_validate(created_group)


@router.get("")
async def list_groups_endpoint(db_session: DbSessionDep, user: ApprovedUser) -> list[SummaryGroupResponse]:
    """要約グループの一覧を取得する.

    Args:
        db_session (AsyncSession): SQLAlchemy の非同期セッション.
        user (User): 現在のユーザー.

    Returns:
        list[SummaryGroupResponse]: 要約グループの一覧.
    """
    groups = await list_groups(db_session, user.id)
    return [SummaryGroupResponse.model_validate(g) for g in groups]


@router.patch("/{group_id}")
async def update_group_endpoint(
    group_id: UUID,
    body: SummaryGroupEdit,
    db_session: DbSessionDep,
    user: ApprovedUser,
) -> SummaryGroupResponse:
    """要約グループの名前を変更する.

    Args:
        group_id (UUID): 変更対象の要約グループの ID.
        body (SummaryGroupEdit): 変更内容.
        db_session (AsyncSession): SQLAlchemy の非同期セッション.
        user (User): 現在のユーザー.

    Returns:
        SummaryGroupResponse: 変更後の要約グループの情報.

    Raises:
        HTTPException: 要約グループが見つからない場合
        HTTPException: 同じ名前の要約グループが既に存在する場合
    """
    group = await get_owned_group(db_session, user.id, group_id)
    if group is None:
        raise HTTPException(status_code=404, detail="Summary group not found")
    try:
        updated_group = await rename_group(db_session, group, body.name)
    except IntegrityError as exc:
        await db_session.rollback()
        raise HTTPException(status_code=400, detail="同じ名前の要約グループが既に存在します") from exc
    return SummaryGroupResponse.model_validate(updated_group)


@router.delete("/{group_id}", status_code=204)
async def delete_group_endpoint(group_id: UUID, db_session: DbSessionDep, user: ApprovedUser) -> None:
    """フォルダを削除する. 中の要約は未分類に戻る. 見つからなければ 404.

    Args:
        group_id (UUID): フォルダの ID.
        db_session (AsyncSession): SQLAlchemy の非同期セッション.
        user (User): 現在のユーザー.

    Raises:
        HTTPException: 404 - フォルダが見つからない場合.
    """
    group = await get_owned_group(db_session, user.id, group_id)
    if group is None:
        raise HTTPException(status_code=404, detail="Group not found")
    await delete_group(db_session, group)
