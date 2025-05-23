from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker

from app.config import DATABASE_PATH

DATABASE_URL = f"sqlite:///{DATABASE_PATH}"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def init_db():
    # Import models here so that SQLAlchemy is aware of them before creating
    # tables. This prevents circular import issues at module load time.
    import app.models  # noqa: F401

    Base.metadata.create_all(bind=engine)
