from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class UserPublic(BaseModel):
    """ユーザー本人に返してよい公開プロフィール (ORM の User 行から生成する)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="ユーザーの一意識別子")
    email: str | None = Field(None, description="ユーザーのメールアドレス")
    name: str = Field("", description="ユーザーのフルネーム")
