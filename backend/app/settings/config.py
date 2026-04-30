from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = Field(..., description="The URL for the database connection")


settings = Settings()  # type: ignore