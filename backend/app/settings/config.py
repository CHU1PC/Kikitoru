import asyncio

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    HF_TOKEN: str = Field(..., description="The Hugging Face token")
    DATABASE_URL: str = Field(..., description="The URL for the database connection")

    # STT Settings
    STT_POOL_SIZE: int = Field(5, description="Number of concurrent STT model instances")
    STT_IDLE_TIMEOUT_SECONDS: int = Field(300, description="Seconds before an idle STT model is unloaded")

    # LLM Settings
    GOOGLE_API_KEY: SecretStr = Field(..., description="API key for Google services")
    LLM_CONCURRENT_LIMIT: int = Field(80, description="Max concurrent requests to the LLM")
    LLM_TIMEOUT_SECONDS: int = Field(..., description="The timeout in seconds for LLM responses")

    # CORS Settings
    ALLOWED_ORIGINS: list[str] = Field(
        default=["http://localhost:5173"],
        description="Comma-separated list of allowed origins for CORS",
    )


settings = Settings()  # type: ignore[call-arg]

llm_semaphore = asyncio.Semaphore(settings.LLM_CONCURRENT_LIMIT)
