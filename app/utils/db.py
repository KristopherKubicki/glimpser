"""Database utilities for initializing the SQLite engine and schema."""

import os

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

    ensure_columns(table_name, [(column_name, column_type, default)])


def ensure_columns(table_name: str, definitions: list[tuple[str, str, str]]) -> None:
    """Upgrade a table using one schema read and transaction per batch.

    Template managers are created on capture and UI read paths. Inspecting the
    same table separately for every optional column made reads CPU-intensive.
    Read the schema anew here (no stale cache across database swaps or forks).
    """

    with engine.begin() as conn:
        table_exists = conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name=:name"),
            {"name": table_name},
        ).fetchone()
        if not table_exists:
            return
        result = conn.execute(text(f"PRAGMA table_info({table_name})"))
        columns = {row[1] for row in result}
        for column_name, column_type, default in definitions:
            if column_name in columns:
                continue
            try:
                conn.execute(
                    text(
                        "ALTER TABLE "
                        f"{table_name} ADD COLUMN {column_name} {column_type} "
                        f"DEFAULT {default}"
                    )
                )
            except OperationalError as exc:
                # Parallel workers can both observe the missing column and race
                # into the ALTER TABLE. Treat duplicate-column errors as a
                # successful concurrent migration.
                if "duplicate column name" not in str(exc).lower():
                    raise
            columns.add(column_name)


def commit_with_retry(session, attempts: int = 3, delay: float = 0.1) -> None:
    """Commit pending work or propagate the original database failure.

    The legacy name and arguments remain compatible with existing callers.
    Retrying only commit after rollback discards pending ORM changes and can
    falsely report success. A safe retry must replay the complete operation in
    a new transaction; this helper cannot reconstruct arbitrary caller work.
    Callers remain responsible for rollback/close on failure. SQLite's existing
    connection busy timeout still handles short-lived write contention.
    """
    session.commit()
