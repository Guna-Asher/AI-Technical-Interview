from functools import lru_cache
from typing import Annotated

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings, read from environment variables."""

    model_config = SettingsConfigDict(extra="ignore")

    database_url: str
    chroma_host: str = "chroma"
    chroma_port: int = 8000
    # NoDecode: accept a plain comma-separated string instead of JSON.
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:3000"]

    # Knowledge base (RAG). Operational settings only; no content is configured here.
    knowledge_dir: str = "/knowledge"
    chroma_collection: str = "knowledge"
    embedding_model: str = "all-MiniLM-L6-v2"
    chunk_size: int = 800  # characters; MiniLM truncates input at about 1000 characters
    chunk_overlap: int = 150  # characters
    retrieval_top_k: int = 5
    # Minimum cosine similarity to return a chunk. An uncalibrated starting value: a similarity score is
    # a ranking signal, not a probability or a reliable confidence measure.
    retrieval_min_score: float = 0.25

    # Not used until the LLM phase; optional so the app starts without them.
    openrouter_api_key: str | None = None
    openrouter_model: str | None = None

    @field_validator("cors_origins", mode="before")
    @classmethod
    def split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @model_validator(mode="after")
    def check_chunking(self) -> "Settings":
        if self.chunk_size <= 0:
            raise ValueError("CHUNK_SIZE must be greater than 0")
        if not 0 <= self.chunk_overlap < self.chunk_size:
            raise ValueError("CHUNK_OVERLAP must be at least 0 and less than CHUNK_SIZE")
        if self.retrieval_top_k <= 0:
            raise ValueError("RETRIEVAL_TOP_K must be greater than 0")
        return self

    @field_validator("openrouter_api_key", "openrouter_model", mode="before")
    @classmethod
    def blank_to_none(cls, value: object) -> object:
        return value or None


@lru_cache
def get_settings() -> Settings:
    return Settings()
