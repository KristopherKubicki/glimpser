from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy import Column, Integer, String, Text, Boolean, Float
from sqlalchemy.exc import SQLAlchemyError
import logging
from contextlib import contextmanager

from app.config import DATABASE_PATH

DATABASE_URL = f"sqlite:///{DATABASE_PATH}"

# Configure SQLite to use Write-Ahead Logging
@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, _):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()

# Create engine with connection pooling and timeout
engine = create_engine(
    DATABASE_URL,
    pool_size=5,
    max_overflow=10,
    pool_timeout=30,
    connect_args={"check_same_thread": False}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

@contextmanager
def get_db_session():
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except SQLAlchemyError as e:
        session.rollback()
        logging.error("Database error: %s", str(e))
        raise
    finally:
        session.close()

def init_db():
    try:
        Base.metadata.create_all(bind=engine)
        logging.info("Database initialized successfully")
    except SQLAlchemyError as e:
        logging.error("Error initializing database: %s", str(e))
        raise

def execute_query(query, params=None):
    with get_db_session() as session:
        try:
            result = session.execute(query, params)
            return result
        except SQLAlchemyError as e:
            logging.error("Query execution error: %s", str(e))
            raise

def add_object(obj):
    with get_db_session() as session:
        try:
            session.add(obj)
            session.flush()
            return obj
        except SQLAlchemyError as e:
            logging.error("Error adding object: %s", str(e))
            raise

def delete_object(obj):
    with get_db_session() as session:
        try:
            session.delete(obj)
            session.flush()
        except SQLAlchemyError as e:
            logging.error("Error deleting object: %s", str(e))
            raise
