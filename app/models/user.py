from sqlalchemy import Column, Integer, String

from app.utils.db import Base


class User(Base):
    __tablename__ = "users"

    ROLE_ADMIN = "admin"
    ROLE_USER = "user"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(String, nullable=False, default=ROLE_USER)

    def __repr__(self) -> str:
        return f"<User id={self.id} username={self.username}>"
