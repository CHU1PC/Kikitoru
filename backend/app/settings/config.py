from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    HF_TOKEN: str = Field(..., description="The Hugging Face token")
    DATABASE_URL: str = Field(..., description="The URL for the database connection")

    # LLM Settings
    GOOGLE_API_KEY: SecretStr = Field(..., description="API key for Google services")
    LLM_CONCURRENT_LIMIT: int = Field(..., description="The concurrent limit for the LLM")
    LLM_TIMEOUT_SECONDS: int = Field(..., description="The timeout in seconds for LLM responses")


settings = Settings()  # type: ignore[call-arg]
