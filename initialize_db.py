import os
from sqlalchemy import Column, Integer, String, Text, Boolean, Float
from sqlalchemy.ext.declarative import declarative_base
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# from app.models import Template, Setting

Base = declarative_base()

class Template(Base):
    __tablename__ = "templates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, unique=True, nullable=False)
    frequency = Column(Integer, default=60)
    timeout = Column(Integer, default=10)
    notes = Column(Text, default="")
    motion_filter = Column(String, default="")
    last_caption = Column(Text, default="")
    last_caption_time = Column(String, default="")
    last_motion_caption = Column(Text, default="")
    last_motion_time = Column(Text, default="")
    last_screenshot_time = Column(Text, default="")
    last_video_time = Column(Text, default="")
    object_filter = Column(String, default="")
    object_confidence = Column(Float, default=0.5)
    popup_xpath = Column(String, default="")
    dedicated_xpath = Column(String, default="")
    callback_url = Column(String, default="")
    proxy = Column(String, default="")
    url = Column(String, default="")
    groups = Column(String, default="")
    invert = Column(Boolean, default=False)
    dark = Column(Boolean, default=False)
    headless = Column(Boolean, default=True)
    stealth = Column(Boolean, default=False)
    browser = Column(Boolean, default=False)
    livecaption = Column(Boolean, default=False)
    danger = Column(Boolean, default=False)
    motion = Column(Float, default=0.2)
    rollback_frames = Column(Integer, default=0)

class Setting(Base):
    __tablename__ = "settings"

    name = Column(String, primary_key=True)
    value = Column(String)


def init_db():
    # Ensure the data directory exists
    #
    DATABASE_PATH = os.getenv("GLIMPSER_DATABASE_PATH", "data/glimpser.db")
    # Create the database engine
    engine = create_engine(f'sqlite:///{DATABASE_PATH}')
    os.makedirs(os.path.dirname(engine.url.database), exist_ok=True)




    # Create all tables
    Base.metadata.create_all(bind=engine)

    print(f"Database initialized at {engine.url.database}")

if __name__ == "__main__":
    init_db()
