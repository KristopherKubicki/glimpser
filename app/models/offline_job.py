"""Database model for jobs queued while running offline."""

from sqlalchemy import Column, Integer, String, Text

from app.utils.db import Base


class OfflineJob(Base):
    """Queued job that could not run due to offline mode."""

    __tablename__ = "offline_jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    function = Column(String, nullable=False)
    args = Column(Text, nullable=False)
    timeout = Column(Integer, nullable=False)
    timestamp = Column(Integer, nullable=False)

    def __repr__(self) -> str:
        return f"<OfflineJob id={self.id} function={self.function}>"
