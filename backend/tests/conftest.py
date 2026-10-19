import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.db_safety import DEV_DATABASE_NAME, DEV_URL, TEST_DATABASE_NAME, TEST_URL, assert_safe_test_database

# Point the app (and Alembic) in this test process at the test database before the app is imported.
os.environ["DATABASE_URL"] = TEST_URL.render_as_string(hide_password=False)

BACKEND_DIR = Path(__file__).resolve().parents[1]
TABLES = "interview_sessions, interview_questions, candidate_answers, interview_reports"


@pytest.fixture(scope="session")
def migrated_database() -> Iterator[None]:
    """Recreate the dedicated test database and apply the real Alembic migrations to it."""
    admin_engine = create_engine(DEV_URL.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as conn:
        assert_safe_test_database(TEST_DATABASE_NAME, DEV_DATABASE_NAME)
        conn.execute(text(f'DROP DATABASE IF EXISTS "{TEST_DATABASE_NAME}" WITH (FORCE)'))
        assert_safe_test_database(TEST_DATABASE_NAME, DEV_DATABASE_NAME)
        conn.execute(text(f'CREATE DATABASE "{TEST_DATABASE_NAME}"'))
    admin_engine.dispose()

    alembic_config = Config(str(BACKEND_DIR / "alembic.ini"))
    alembic_config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    command.upgrade(alembic_config, "head")
    yield


@pytest.fixture
def db(migrated_database: None) -> Iterator[Session]:
    """A session on the test database; all tables are emptied afterwards."""
    from app.database import SessionLocal, engine

    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        with engine.begin() as conn:
            current = conn.execute(text("SELECT current_database()")).scalar_one()
            assert_safe_test_database(current, DEV_DATABASE_NAME)
            conn.execute(text(f"TRUNCATE {TABLES} CASCADE"))


@pytest.fixture
def api_client(db: Session) -> Iterator[TestClient]:

    from app.main import app

    with TestClient(app) as client:
        yield client


@pytest.fixture
def rag_collection(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[str]:
    """A throwaway Chroma collection name; settings are pointed at it and at an empty temp knowledge dir.

    Tests never touch the real knowledge collection: the name must start with "pytest_" before anything is deleted.
    """
    import uuid

    from app.config import get_settings
    from app.rag.store import get_client

    name = f"pytest_{uuid.uuid4().hex[:8]}"
    knowledge_dir = tmp_path / "knowledge"
    knowledge_dir.mkdir()
    monkeypatch.setenv("CHROMA_COLLECTION", name)
    monkeypatch.setenv("KNOWLEDGE_DIR", str(knowledge_dir))
    get_settings.cache_clear()
    assert get_settings().chroma_collection.startswith("pytest_")
    try:
        yield name
    finally:
        assert name.startswith("pytest_"), "refusing to delete a non-test collection"
        try:
            get_client().delete_collection(name)
        except Exception:
            pass  # never created
        monkeypatch.undo()
        get_settings.cache_clear()


# Synthetic passages used only to seed a throwaway test collection.
SEED_PASSAGES = {
    "a.pdf": [
        "Database indexes speed up queries. Query tuning with postgres explain plans reduces latency.",
        "Caching layers reduce latency. Cache invalidation is hard, and caching improves backend role performance.",
    ],
    "b.pdf": [
        "Threads and locks coordinate concurrent backend work. Query tuning also involves concurrency.",
        "Tomato seedlings need sunlight and regular watering in the garden.",
    ],
}


@pytest.fixture
def seeded_knowledge(rag_collection: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> str:
    """Ingest synthetic PDFs into the throwaway collection and make retrieval use the deterministic fake embedder."""
    from app.config import get_settings
    from app.rag.ingest import ingest_directory
    from tests.rag_helpers import fake_embed, make_pdf

    monkeypatch.setenv("RETRIEVAL_MIN_SCORE", "0.05")  # the fake embedder's scores are not comparable to the real model's
    get_settings.cache_clear()
    monkeypatch.setattr("app.rag.retrieval.embed_texts", fake_embed)
    directory = tmp_path / "seed"
    for name, pages in SEED_PASSAGES.items():
        make_pdf(directory / name, pages)
    ingest_directory(directory, collection_name=rag_collection, embedder=fake_embed, model_name="fake")
    return rag_collection
