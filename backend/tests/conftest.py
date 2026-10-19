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
