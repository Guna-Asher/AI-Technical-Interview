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

    # OpenRouter. Key and model are optional so the app starts without them; LLM operations
    # raise a clear configuration error when they are missing.
    openrouter_api_key: str | None = None
    openrouter_model: str | None = None
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_timeout_seconds: float = 60.0
    llm_max_attempts: int = 2  # one retry when the model returns invalid output

    # Resume upload limits.
    max_resume_bytes: int = 5 * 1024 * 1024
    max_resume_chars: int = 20_000  # text beyond this is not sent to the model

    # Question generation (operational limits; uncalibrated heuristics, not interview content).
    question_count: int = 5
    context_chunks: int = 8  # retrieved passages passed to the model
    min_context_chunks: int = 3  # fewer relevant passages than this means no questions are generated
    max_retrieval_queries: int = 4

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
        positive = {
            "OPENROUTER_TIMEOUT_SECONDS": self.openrouter_timeout_seconds,
            "LLM_MAX_ATTEMPTS": self.llm_max_attempts,
            "MAX_RESUME_BYTES": self.max_resume_bytes,
            "MAX_RESUME_CHARS": self.max_resume_chars,
            "QUESTION_COUNT": self.question_count,
            "CONTEXT_CHUNKS": self.context_chunks,
            "MIN_CONTEXT_CHUNKS": self.min_context_chunks,
            "MAX_RETRIEVAL_QUERIES": self.max_retrieval_queries,
        }
        for name, value in positive.items():
            if value <= 0:
                raise ValueError(f"{name} must be greater than 0")
        if self.min_context_chunks > self.context_chunks:
            raise ValueError("MIN_CONTEXT_CHUNKS must not exceed CONTEXT_CHUNKS")
        return self

    @field_validator("openrouter_api_key", "openrouter_model", mode="before")
    @classmethod
    def blank_to_none(cls, value: object) -> object:
        return value or None


@lru_cache
def get_settings() -> Settings:
    return Settings()
