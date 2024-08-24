from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy import Column, Integer, String, Text, Boolean, Float, LargeBinary
from sqlalchemy.ext.declarative import declared_attr
from sqlalchemy.engine.result import ScalarResult

from app.config import DATABASE_PATH
from app.utils.encryption import encrypt_data, decrypt_data

DATABASE_URL = f"sqlite:///{DATABASE_PATH}"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

class EncryptedBase:
    @declared_attr
    def __tablename__(cls):
        return cls.__name__.lower()

    id = Column(Integer, primary_key=True, index=True)

    @classmethod
    def encrypt_field(cls, field_name):
        def getter(self):
            value = getattr(self, f'_{field_name}')
            return decrypt_data(value) if value else None

        def setter(self, value):
            if value is not None:
                value = encrypt_data(value)
            setattr(self, f'_{field_name}', value)

        return property(getter, setter)

Base = declarative_base(cls=EncryptedBase)

def init_db():
    Base.metadata.create_all(bind=engine)

@event.listens_for(engine, "before_cursor_execute")
def encrypt_bind_param(conn, cursor, statement, parameters, context, executemany):
    if executemany:
        parameters = [
            {k: encrypt_data(v) if isinstance(v, str) else v for k, v in param.items()}
            for param in parameters
        ]
    else:
        parameters = {k: encrypt_data(v) if isinstance(v, str) else v for k, v in parameters.items()}

@event.listens_for(engine, "result_scalar")
def decrypt_result_scalar(state, scalar):
    try:
        return decrypt_data(scalar)
    except:
        return scalar
