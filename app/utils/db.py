from sqlalchemy import create_engine, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy import Column, Integer, String, Text, Boolean, Float
from sqlalchemy.exc import SQLAlchemyError
import logging

from app.config import DATABASE_PATH

DATABASE_URL = f"sqlite:///{DATABASE_PATH}"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def init_db():
    Base.metadata.create_all(bind=engine)

def check_db_connection():
    try:
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        logging.info("Database connection successful")
        return True
    except SQLAlchemyError as e:
        logging.error(f"Database connection failed: {str(e)}")
        return False
    finally:
        db.close()
