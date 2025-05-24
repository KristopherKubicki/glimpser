from datetime import datetime
from sqlalchemy import Column, Integer, Text, DateTime

from app.utils.db import Base

class Summary(Base):
    __tablename__ = "summaries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<Summary id={self.id} created_at={self.created_at}>"
