from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    HF_TOKEN: str = Field(..., description="The Hugging Face token")
    DATABASE_URL: str = Field(..., description="The URL for the database connection")


settings = Settings()  # type: ignore[call-arg]
