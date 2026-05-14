from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    HF_TOKEN: str = Field(..., description="The Hugging Face token")
    DATABASE_URL: str = Field(..., description="The URL for the database connection")

    # STT Settings
    STT_POOL_SIZE: int = Field(5, description="Number of concurrent STT model instances")

    # LLM Settings
    GOOGLE_API_KEY: SecretStr = Field(..., description="API key for Google services")
    LLM_TIMEOUT_SECONDS: int = Field(..., description="The timeout in seconds for LLM responses")


settings = Settings()  # type: ignore[call-arg]
