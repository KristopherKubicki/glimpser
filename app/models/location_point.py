"""Latest known location for a tracked phone, vehicle, or bridge source."""

from datetime import datetime

from sqlalchemy import Column, DateTime, Float, Integer, String, Text

from app.utils.db import Base


class LocationPoint(Base):
    """Store the current normalized location for one tracked subject."""

    __tablename__ = "location_points"

    id = Column(Integer, primary_key=True, autoincrement=True)
    subject_id = Column(String, unique=True, index=True, nullable=False)
    label = Column(String, nullable=False)
    provider = Column(String, nullable=False, default="android")
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    accuracy_m = Column(Float, nullable=True)
    altitude_m = Column(Float, nullable=True)
    battery_percent = Column(Float, nullable=True)
    speed_mps = Column(Float, nullable=True)
    heading_degrees = Column(Float, nullable=True)
    timestamp = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    stale_after_seconds = Column(Integer, nullable=False, default=1800)
    metadata_json = Column(Text, nullable=False, default="{}")

    def __repr__(self) -> str:
        return (
            f"<LocationPoint subject_id={self.subject_id!r} provider={self.provider!r}>"
        )
