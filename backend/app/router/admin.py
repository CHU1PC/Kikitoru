from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import col, select

from app.db.models import User, UserRole, UserStatus
from app.dependencies import AdminUser, DbSessionDep, get_admin_user
from app.schema.users import UserAdminUpdate, UserPublic

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(get_admin_user)])


@router.get("/users")
async def list_users_endpoint(
    db_session: DbSessionDep,
    user_status: Annotated[UserStatus | None, Query(alias="status")] = None
) -> list[UserPublic]:
    """管理者が全ユーザーの一覧を取得するエンドポイント.

    Args:
        db_session (AsyncSession): SQLAlchemy の非同期セッション.
        user_status (UserStatus | None): ユーザーの状態でフィルタリングする場合は指定する.
            None の場合は全ユーザーを取得する.

    Returns:
        list[UserPublic]: ユーザーの公開プロフィールのリスト
    """
    query = select(User)
    if user_status is not None:
        query = query.where(col(User.status) == user_status)
    rows = (await db_session.exec(query.order_by(col(User.created_at).desc()))).all()
    return [UserPublic.model_validate(row) for row in rows]


@router.patch("/users/{user_id}")
async def update_user_endpoint(
    user_id: UUID,
    payload: UserAdminUpdate,
    db_session: DbSessionDep,
    admin: AdminUser
) -> UserPublic:
    """ユーザーの status / role を部分更新するエンドポイント. 管理者のみアクセス可能.

    Args:
        user_id (UUID): 更新対象のユーザーの一意識別子
        payload (UserAdminUpdate): 更新内容を含むペイロード
        db_session (AsyncSession): SQLAlchemy の非同期セッション.
        admin (User): 管理者ユーザー. FastAPI の依存性注入で解決される.

    Returns:
        UserPublic: 更新後のユーザーの公開プロフィール

    Raises:
        HTTPException: 404 - 指定されたユーザーが存在しない場合
        HTTPException: 400 - 管理者が自分自身の role を user に変更しようとした場合、
            または自分自身の status を rejected に変更しようとした場合
    """
    target = await db_session.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if target.id == admin.id and (payload.status == UserStatus.rejected or payload.role == UserRole.user):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot demote or reject yourself")
    if payload.status is not None:
        target.status = payload.status
    if payload.role is not None:
        target.role = payload.role
    await db_session.commit()
    await db_session.refresh(target)
    return UserPublic.model_validate(target)
