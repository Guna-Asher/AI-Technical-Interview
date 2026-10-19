"""Names and guard for the dedicated test database.

The test database is always "<development name>_test", so the test suite can never be pointed at
the development database. Import this module only as `tests.db_safety` (a single import path).
"""

import os

from sqlalchemy.engine import URL, make_url

_DEFAULT_URL = "postgresql+psycopg://interview:change-me@postgres:5432/interview"

DEV_URL: URL = make_url(os.environ.get("DATABASE_URL", _DEFAULT_URL))
DEV_DATABASE_NAME: str = str(DEV_URL.database)

if DEV_DATABASE_NAME.endswith("_test"):
    raise RuntimeError(
        f"DATABASE_URL already points at '{DEV_DATABASE_NAME}'; "
        "the test suite derives its own '<name>_test' database from the development database."
    )

TEST_DATABASE_NAME: str = f"{DEV_DATABASE_NAME}_test"
TEST_URL: URL = DEV_URL.set(database=TEST_DATABASE_NAME)


def assert_safe_test_database(name: str, dev_name: str) -> None:
    """Raise unless `name` is a dedicated test database distinct from the development one."""
    if name == dev_name or not name.endswith("_test"):
        raise RuntimeError(f"Refusing to modify database '{name}': not a dedicated test database.")
