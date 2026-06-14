from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class UserPublic(BaseModel):
    """ユーザー本人に返してよい公開プロフィール (ORM の User 行から生成する)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="Unique identifier of the user")
    email: str | None = Field(None, description="Email address of the user")
    name: str = Field("", description="Full name of the user")
