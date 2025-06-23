"""Database model for daily log summaries."""

from sqlalchemy import Column, Integer, String, Text

from app.utils.db import Base


class LogSummary(Base):
    """Summarized log entry for a given day."""

    __tablename__ = "log_summaries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(Integer, nullable=False)
    camera = Column(String, default="", nullable=False)
    content = Column(Text, nullable=False)

    def __repr__(self) -> str:
        return f"<LogSummary id={self.id} camera={self.camera} ts={self.timestamp}>"
