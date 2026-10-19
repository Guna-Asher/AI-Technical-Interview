"""Chroma access. Chroma holds the knowledge chunks; PostgreSQL holds application data."""

from functools import lru_cache

import chromadb
from chromadb.api import ClientAPI
from chromadb.api.models.Collection import Collection
from chromadb.errors import NotFoundError

from app.config import get_settings


class KnowledgeBaseError(Exception):
    """The knowledge base (Chroma) could not be reached."""


@lru_cache
def get_client() -> ClientAPI:
    settings = get_settings()
    try:
        return chromadb.HttpClient(host=settings.chroma_host, port=settings.chroma_port)
    except Exception as exc:
        raise KnowledgeBaseError(
            f"Cannot connect to Chroma at {settings.chroma_host}:{settings.chroma_port}: {exc}"
        ) from exc


def get_collection(name: str | None = None, *, create: bool = False) -> Collection | None:
    """Return the collection, or None if it does not exist and `create` is False.

    Embeddings are always computed by this application and passed in explicitly,
    so Chroma's own embedding function is disabled.
    """
    name = name or get_settings().chroma_collection
    client = get_client()
    try:
        if create:
            return client.get_or_create_collection(
                name, configuration={"hnsw": {"space": "cosine"}}, embedding_function=None
            )
        return client.get_collection(name, embedding_function=None)
    except NotFoundError:
        return None
    except Exception as exc:
        raise KnowledgeBaseError(f"Chroma request failed: {exc}") from exc
