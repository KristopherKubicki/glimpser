from sqlalchemy import Column, Integer, String, DateTime
from app.utils.db import Base
import datetime


class Log(Base):
    __tablename__ = "logs"

    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    level = Column(String)
    message = Column(String)
    source = Column(String)

    def __repr__(self):
        return f"<Log(id={self.id}, timestamp={self.timestamp}, level={self.level}, source={self.source})>"
