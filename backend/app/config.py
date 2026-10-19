from functools import lru_cache
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings, read from environment variables."""

    model_config = SettingsConfigDict(extra="ignore")

    database_url: str
    chroma_host: str = "chroma"
    chroma_port: int = 8000
    # NoDecode: accept a plain comma-separated string instead of JSON.
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:3000"]

    # Not used until the LLM phase; optional so the app starts without them.
    openrouter_api_key: str | None = None
    openrouter_model: str | None = None

    @field_validator("cors_origins", mode="before")
    @classmethod
    def split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("openrouter_api_key", "openrouter_model", mode="before")
    @classmethod
    def blank_to_none(cls, value: object) -> object:
        return value or None


@lru_cache
def get_settings() -> Settings:
    return Settings()
