from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text

from tests.db_safety import DEV_DATABASE_NAME, TEST_DATABASE_NAME, assert_safe_test_database

BACKEND_DIR = Path(__file__).resolve().parents[1]


def test_migration_creates_tables_at_head(migrated_database: None) -> None:
    from app.database import engine

    script = ScriptDirectory(str(BACKEND_DIR / "alembic"))
    with engine.connect() as conn:
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    tables = set(inspect(engine).get_table_names())

    assert version == script.get_current_head()
    assert {"interview_sessions", "interview_questions", "candidate_answers", "interview_reports"} <= tables


def test_test_suite_uses_a_dedicated_database(migrated_database: None) -> None:
    from app.database import engine

    with engine.connect() as conn:
        current = conn.execute(text("SELECT current_database()")).scalar_one()

    assert engine.url.database == TEST_DATABASE_NAME == current
    assert current.endswith("_test")
    assert current != DEV_DATABASE_NAME


@pytest.mark.parametrize("name, dev_name", [("interview", "interview"), ("interview_test", "interview_test"), ("other", "interview")])
def test_guard_rejects_non_test_databases(name: str, dev_name: str) -> None:
    with pytest.raises(RuntimeError):
        assert_safe_test_database(name, dev_name)


def test_guard_accepts_the_derived_test_database() -> None:
    assert_safe_test_database("interview_test", "interview")
