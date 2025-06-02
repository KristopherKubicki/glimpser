from sqlalchemy import Column, Integer, String, Text

from app.utils.db import Base


class Log(Base):
    """Persistent log entry."""

    __tablename__ = "logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(Integer, nullable=False)
    level = Column(String, nullable=False)
    source = Column(String, nullable=False)
    message = Column(Text, nullable=False)

    def __repr__(self) -> str:
        return f"<Log id={self.id} level={self.level}>"
