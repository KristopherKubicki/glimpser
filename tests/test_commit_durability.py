import sqlite3

import pytest
from sqlalchemy import Column, Integer, String, create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, declarative_base

from app.utils.db import commit_with_retry

Base = declarative_base()


class StoredValue(Base):
    __tablename__ = "durability_values"
    id = Column(Integer, primary_key=True)
    value = Column(String)


@pytest.mark.parametrize("mutation", ["insert", "update", "delete"])
def test_locked_write_never_reports_empty_commit_success(tmp_path, mutation):
    path = tmp_path / "durability.sqlite"
    engine = create_engine(f"sqlite:///{path}", connect_args={"timeout": 0.01})
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as session:
            session.add(StoredValue(id=1, value="before"))
            session.commit()
        with Session(engine) as session:
            if mutation == "insert":
                session.add(StoredValue(id=2, value="new"))
            else:
                row = session.get(StoredValue, 1)
                if mutation == "update":
                    row.value = "after"
                else:
                    session.delete(row)
            writer = sqlite3.connect(path)
            writer.execute("BEGIN IMMEDIATE")
            try:
                with pytest.raises(OperationalError, match="database is locked"):
                    commit_with_retry(session, attempts=2, delay=0)
            finally:
                writer.rollback()
                writer.close()
        with Session(engine) as session:
            assert session.get(StoredValue, 1).value == "before"
            assert session.get(StoredValue, 2) is None
            # Replaying the complete operation after contention clears is safe.
            if mutation == "insert":
                session.add(StoredValue(id=2, value="new"))
            elif mutation == "update":
                session.get(StoredValue, 1).value = "after"
            else:
                session.delete(session.get(StoredValue, 1))
            commit_with_retry(session)
        with Session(engine) as session:
            if mutation == "insert":
                assert session.get(StoredValue, 2).value == "new"
            elif mutation == "update":
                assert session.get(StoredValue, 1).value == "after"
            else:
                assert session.get(StoredValue, 1) is None
    finally:
        engine.dispose()
