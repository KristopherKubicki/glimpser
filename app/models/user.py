"""Database model for application users."""

from sqlalchemy import Boolean, Column, Integer, String

from app.utils.db import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(String, nullable=True)
    temp_password_required = Column(Boolean, nullable=False, default=False)

    def __repr__(self) -> str:
        return f"<User id={self.id} username={self.username}>"
