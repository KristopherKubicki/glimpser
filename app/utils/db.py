import time
import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy import Column, Integer, String, Text, Boolean, Float
from sqlalchemy.exc import SQLAlchemyError, OperationalError

from app.config import DATABASE_PATH

DATABASE_URL = f"sqlite:///{DATABASE_PATH}"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db_connection(max_retries=3, retry_delay=1):
    for attempt in range(max_retries):
        try:
            db = SessionLocal()
            db.execute("SELECT 1")  # Test the connection
            return db
        except SQLAlchemyError as e:
            if attempt < max_retries - 1:
                logging.warning(f"Database connection attempt {attempt + 1} failed. Retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
            else:
                logging.error(f"Failed to establish database connection after {max_retries} attempts: {str(e)}")
                raise
    return None

def init_db():
    try:
        Base.metadata.create_all(bind=engine)
        logging.info("Database initialized successfully")
    except SQLAlchemyError as e:
        logging.error(f"Error initializing database: {str(e)}")
        raise
