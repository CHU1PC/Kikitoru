import asyncio

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    HF_TOKEN: SecretStr = Field(..., description="The Hugging Face token")
    DATABASE_URL: SecretStr = Field(..., description="The URL for the database connection")
    DATABASE_SSL_MODE: str = Field(
        default="disable",
        description=(
            "PostgreSQL SSL mode for asyncpg. 'disable' is fine when the backend "
            "and DB run on the same host (e.g., docker-compose). Set to 'require' "
            "or higher when connecting to a managed DB or across the network."
        ),
    )

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

    # Deployment
    ENABLE_DOCS: bool = Field(
        default=True,
        description="Whether to expose /docs, /redoc, /openapi.json. Set to false in production.",
    )


settings = Settings()  # type: ignore[call-arg]

llm_semaphore = asyncio.Semaphore(settings.LLM_CONCURRENT_LIMIT)
