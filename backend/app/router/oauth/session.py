from fastapi import APIRouter

from app.dependencies import CurrentUser
from app.schema.users import UserPublic

router = APIRouter()


@router.get("/me")
async def get_me(user: CurrentUser) -> UserPublic:
    """現在ログイン中のユーザーを返す.

    Args:
        user (User): セッション Cookie から復元された現在のユーザー.

    Returns:
        UserPublic: 公開してよいユーザープロフィール.
    """
    return UserPublic.model_validate(user)
