from sqlalchemy import Column, Integer, String, Text, Boolean

from app.utils.db import Base


class Notification(Base):
    """User-facing notification stored in the database."""

    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(Integer, nullable=False)
    title = Column(String, nullable=False)
    body = Column(Text, nullable=False)
    viewed = Column(Boolean, default=False)

    def __repr__(self) -> str:
        return f"<Notification id={self.id} title={self.title}>"
