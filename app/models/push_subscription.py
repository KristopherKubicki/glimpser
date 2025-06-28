"""Database model for Web Push subscription information."""

from sqlalchemy import Column, ForeignKey, Integer, String, Text

from app.utils.db import Base


class PushSubscription(Base):
    """Web Push subscription info for a user."""

    __tablename__ = "push_subscriptions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    endpoint = Column(Text, unique=True, nullable=False)
    auth = Column(String, nullable=False)
    p256dh = Column(String, nullable=False)
    created_at = Column(Integer, nullable=False)

    def __repr__(self) -> str:
        return f"<PushSubscription id={self.id} user_id={self.user_id}>"
