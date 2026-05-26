import asyncio
import json
from typing import Annotated

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    HF_TOKEN: SecretStr = Field(..., description="The Hugging Face token")
    DATABASE_URL: SecretStr = Field(..., description="The URL for the database connection")
    DATABASE_SSL_MODE: str = Field(
        default="disable",
        description=(
            "PostgreSQL SSL mode for asyncpg. 'disable' (plaintext) is fine only "
            "when the backend and DB share a host (e.g., docker-compose). For a "
            "managed DB or any connection across the network use 'verify-full', "
            "which authenticates the server certificate and hostname."
        ),
    )

    # STT Settings
    STT_POOL_SIZE: int = Field(5, description="Number of concurrent STT model instances")
    STT_IDLE_TIMEOUT_SECONDS: int = Field(300, description="Seconds before an idle STT model is unloaded")

    # LLM Settings
    GOOGLE_API_KEY: SecretStr = Field(..., description="API key for Google services")
    LLM_CONCURRENT_LIMIT: int = Field(80, description="Max concurrent requests to the LLM")
    LLM_TIMEOUT_SECONDS: int = Field(..., description="The timeout in seconds for LLM responses")

    ALLOWED_ORIGINS: Annotated[list[str], NoDecode] = Field(
        default=["http://localhost:5173"],
        description='Allowed CORS origins. Comma-separated (a,b) or a JSON array (["a","b"]).',
    )

    @field_validator("ALLOWED_ORIGINS", mode="before")
    @classmethod
    def _parse_allowed_origins(cls, value: object) -> object:
        """Accept either a comma-separated string or a JSON array from the env.

        Args:
            value (object): Raw value from the environment (str) or the default (list).

        Returns:
            object: A list of origin strings, or the value unchanged if not a string.
        """
        if isinstance(value, str):
            text = value.strip()
            if text.startswith("["):
                return json.loads(text)
            return [origin.strip() for origin in text.split(",") if origin.strip()]
        return value

    # Deployment
    ENABLE_DOCS: bool = Field(
        default=True,
        description="Whether to expose /docs, /redoc, /openapi.json. Set to false in production.",
    )


settings = Settings()  # type: ignore[call-arg]

llm_semaphore = asyncio.Semaphore(settings.LLM_CONCURRENT_LIMIT)
