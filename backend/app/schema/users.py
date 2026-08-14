from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.db.models import UserRole, UserStatus


class UserPublic(BaseModel):
    """ユーザー本人に返してよい公開プロフィール (ORM の User 行から生成する)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="ユーザーの一意識別子")
    email: str | None = Field(None, description="ユーザーのメールアドレス")
    name: str = Field("", description="ユーザーのフルネーム")
    role: UserRole = Field(..., description="ユーザーの役割")
    status: UserStatus = Field(..., description="ユーザーの状態")


class UserAdminUpdate(BaseModel):
    """一般ユーザーの status と role を管理者が更新するためのスキーマ."""

    role: UserRole | None = Field(None, description="ユーザーの役割")
    status: UserStatus | None = Field(None, description="ユーザーの状態")
