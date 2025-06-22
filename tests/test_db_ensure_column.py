import os
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine, text

from app.utils.db import ensure_column


class TestEnsureColumn(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite:///:memory:", connect_args={"check_same_thread": False}
        )
        with self.engine.begin() as conn:
            conn.execute(text("CREATE TABLE test_table (id INTEGER PRIMARY KEY)"))

    def get_columns(self):
        with self.engine.connect() as conn:
            return [
                row[1] for row in conn.execute(text("PRAGMA table_info(test_table)"))
            ]

    def test_adds_missing_column(self):
        with patch("app.utils.db.engine", self.engine):
            ensure_column("test_table", "name", "TEXT", "''")
        self.assertIn("name", self.get_columns())

    def test_existing_column_unchanged(self):
        with patch("app.utils.db.engine", self.engine):
            before = self.get_columns()
            ensure_column("test_table", "id", "INTEGER", "0")
        self.assertEqual(before, self.get_columns())


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
