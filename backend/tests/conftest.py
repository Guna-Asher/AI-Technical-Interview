import os

# Settings are read at import time; provide a URL so tests don't need a real database.
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://test:test@localhost:5432/test")
