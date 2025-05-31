from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker

from app.config import DATABASE_PATH
import os

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
    # Import models here so that SQLAlchemy is aware of them before creating
    # tables. This prevents circular import issues at module load time.
    import app.models  # noqa: F401

    Base.metadata.create_all(bind=engine)
