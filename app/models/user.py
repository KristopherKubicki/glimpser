from sqlalchemy import Column, Integer, String

from app.utils.db import Base


"""Database model for application users."""


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(String, nullable=True)

    def __repr__(self) -> str:
        return f"<User id={self.id} username={self.username}>"
