from collections.abc import Iterator
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.config import Settings
from app.database import get_db
from app.main import app


@pytest.fixture
def client() -> Iterator[TestClient]:
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_health_ok_when_database_reachable(client: TestClient) -> None:
    app.dependency_overrides[get_db] = lambda: MagicMock()

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


def test_health_503_when_database_unreachable(client: TestClient) -> None:
    failing_db = MagicMock()
    failing_db.execute.side_effect = OperationalError("SELECT 1", {}, Exception("secret detail"))
    app.dependency_overrides[get_db] = lambda: failing_db

    response = client.get("/api/health")

    assert response.status_code == 503
    assert response.json() == {"status": "degraded", "database": "unavailable"}
    assert "secret detail" not in response.text


def test_settings_parse_origins_and_blank_openrouter(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@postgres:5432/db")
    monkeypatch.setenv("CORS_ORIGINS", "http://a.test, http://b.test")
    monkeypatch.setenv("OPENROUTER_API_KEY", "")

    settings = Settings()

    assert settings.cors_origins == ["http://a.test", "http://b.test"]
    assert settings.openrouter_api_key is None


def test_rag_settings_defaults_are_operational_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@postgres:5432/db")
    for name in ("CHUNK_SIZE", "CHUNK_OVERLAP", "KNOWLEDGE_DIR", "CHROMA_COLLECTION", "RETRIEVAL_TOP_K"):
        monkeypatch.delenv(name, raising=False)

    settings = Settings()

    assert (settings.chunk_size, settings.chunk_overlap) == (800, 150)
    assert settings.knowledge_dir == "/knowledge"
    assert settings.chroma_collection == "knowledge"
    assert settings.embedding_model == "all-MiniLM-L6-v2"


@pytest.mark.parametrize(
    "size, overlap, top_k",
    [("0", "0", "5"), ("100", "100", "5"), ("100", "-1", "5"), ("100", "10", "0")],
)
def test_invalid_rag_settings_are_rejected(monkeypatch: pytest.MonkeyPatch, size: str, overlap: str, top_k: str) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@postgres:5432/db")
    monkeypatch.setenv("CHUNK_SIZE", size)
    monkeypatch.setenv("CHUNK_OVERLAP", overlap)
    monkeypatch.setenv("RETRIEVAL_TOP_K", top_k)

    with pytest.raises(ValueError):
        Settings()
