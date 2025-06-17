import os

from sqlalchemy import create_engine, text
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
    """Import models and create database tables."""
    # Import models here so that SQLAlchemy is aware of them before creating
    # tables. This prevents circular import issues at module load time.
    import app.models  # noqa: F401

    Base.metadata.create_all(bind=engine)


def ensure_column(
    table_name: str, column_name: str, column_type: str, default: str
) -> None:
    """Add a column to a table if it doesn't already exist."""

    with engine.begin() as conn:
        result = conn.execute(text(f"PRAGMA table_info({table_name})"))
        columns = [row[1] for row in result]
        if column_name not in columns:
            conn.execute(
                text(
                    f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type} DEFAULT {default}"
                )
            )
