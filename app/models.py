from sqlalchemy import Column, Integer, String, Text
from app.utils.db import Base

class Summary(Base):
    __tablename__ = 'summaries'

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(String, nullable=False)
    content = Column(Text, nullable=False)

    def __repr__(self):
        return f"<Summary(id={self.id}, timestamp={self.timestamp})>"