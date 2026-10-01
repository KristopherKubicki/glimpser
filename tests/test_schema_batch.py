"""Schema batching keeps read paths cheap without caching migration state."""

from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.exc import OperationalError

from app.utils import db


@pytest.fixture
def engine(tmp_path, monkeypatch):
    value = create_engine(f"sqlite:///{tmp_path / 'schema.db'}")
    monkeypatch.setattr(db, "engine", value)
    with value.begin() as conn:
        conn.execute(text("CREATE TABLE sample (id INTEGER PRIMARY KEY)"))
    yield value
    value.dispose()


def test_batch_migrates_once_and_preserves_defaults(engine):
    columns = [("label", "TEXT", "'pending'"), ("enabled", "BOOLEAN", "0")]
    db.ensure_columns("sample", columns)
    statements = []
    event.listen(
        engine, "before_cursor_execute", lambda c, cur, s, *a: statements.append(s)
    )
    db.ensure_columns("sample", columns * 32)
    assert (
        len(statements) == 2
    )  # Existence check and one PRAGMA, independent of batch size.
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO sample(id) VALUES (1)"))
        assert conn.execute(text("SELECT label,enabled FROM sample")).one() == (
            "pending",
            0,
        )


def test_batch_rechecks_recreated_table(engine):
    db.ensure_columns("sample", [("label", "TEXT", "''")])
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE sample"))
        conn.execute(text("CREATE TABLE sample (id INTEGER PRIMARY KEY)"))
    db.ensure_columns("sample", [("label", "TEXT", "''")])
    with engine.connect() as conn:
        assert "label" in {
            r[1] for r in conn.execute(text("PRAGMA table_info(sample)"))
        }


def test_missing_table_remains_noop(engine):
    db.ensure_columns("missing", [("label", "TEXT", "''")])
    with engine.connect() as conn:
        assert not conn.execute(
            text("SELECT name FROM sqlite_master WHERE name='missing'")
        ).first()


def test_parallel_initializers_keep_all_columns(engine):
    columns = [(f"field_{i}", "INTEGER", "0") for i in range(12)]
    with ThreadPoolExecutor(max_workers=4) as workers:
        list(workers.map(lambda _: db.ensure_columns("sample", columns), range(4)))
    with engine.connect() as conn:
        assert len(conn.execute(text("PRAGMA table_info(sample)")).all()) == 13


def test_unexpected_migration_error_is_not_swallowed(engine):
    with pytest.raises(OperationalError):
        db.ensure_columns("sample", [("bad column", "INVALID TYPE (", "0")])
