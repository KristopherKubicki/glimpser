from sqlalchemy import Column, Integer, Text

from app.utils.db import Base


class Summary(Base):
    """Database model for stored summaries."""

    __tablename__ = "summaries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)

    def __repr__(self) -> str:
        return f"<Summary id={self.id} timestamp={self.timestamp}>"
