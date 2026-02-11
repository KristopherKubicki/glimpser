"""Database utilities for initializing the SQLite engine and schema."""

import os
import time

from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import DATABASE_PATH

DATABASE_URL = f"sqlite:///{DATABASE_PATH}"

os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False, "timeout": 30},
)
with engine.connect() as conn:
    conn.execute(text("PRAGMA journal_mode=WAL"))
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def init_db():
    """Create all database tables defined in :mod:`app.models`."""

    # Import models so SQLAlchemy registers them before table creation. This
    # import is intentionally local to avoid circular dependencies at module
    # load time.
    import app.models  # noqa: F401

    try:
        Base.metadata.create_all(bind=engine)
    except OperationalError as exc:
        # When multiple workers initialize the database concurrently the
        # CREATE TABLE commands can race. Ignore "already exists" errors so
        # repeated calls remain idempotent.
        if "already exists" not in str(exc):
            raise


def ensure_column(
    table_name: str, column_name: str, column_type: str, default: str
) -> None:
    """Add a column to a table if it doesn't already exist."""

    with engine.begin() as conn:
        table_exists = conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name=:name"),
            {"name": table_name},
        ).fetchone()
        if not table_exists:
            return
        result = conn.execute(text(f"PRAGMA table_info({table_name})"))
        columns = [row[1] for row in result]
        if column_name not in columns:
            conn.execute(
                text(
                    "ALTER TABLE "
                    f"{table_name} ADD COLUMN {column_name} {column_type} "
                    f"DEFAULT {default}"
                )
            )


def commit_with_retry(session, attempts: int = 3, delay: float = 0.1) -> None:
    """Commit a session with retries on SQLite locking errors."""

    for attempt in range(attempts):
        try:
            session.commit()
            return
        except OperationalError as exc:
            if "database is locked" in str(exc) and attempt < attempts - 1:
                session.rollback()
                time.sleep(delay)
                continue
            raise
