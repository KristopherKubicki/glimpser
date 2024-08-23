import sys
import os
import unittest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.utils.db import init_db, Base, SessionLocal


class TestDB(unittest.TestCase):
    def setUp(self):
        # Create a temporary database for testing
        self.test_db_path = "test_glimpser.db"
        self.test_db_url = f"sqlite:///{self.test_db_path}"
        self.engine = create_engine(self.test_db_url)
        self.TestingSessionLocal = sessionmaker(
            autocommit=False, autoflush=False, bind=self.engine
        )
        Base.metadata.create_all(bind=self.engine)

    def tearDown(self):
        # Remove the temporary database
        Base.metadata.drop_all(bind=self.engine)
        os.remove(self.test_db_path)

    def test_init_db(self):
        # Test that init_db creates the necessary tables
        init_db()
        with self.engine.connect() as conn:
            result = conn.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = [row[0] for row in result]

        # Assert that expected tables are created (you may need to adjust this list)
        expected_tables = ["settings"]  # Add other table names as needed
        for table in expected_tables:
            self.assertIn(table, tables)

    def test_session_creation(self):
        # Test that SessionLocal creates a valid session
        session = SessionLocal()
        self.assertIsNotNone(session)
        session.close()


if __name__ == "__main__":
    unittest.main()
