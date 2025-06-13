import importlib
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


class TestInitDb(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test.db")
        self.env_patch = patch.dict(
            os.environ, {"GLIMPSER_DATABASE_PATH": self.db_path}
        )
        self.env_patch.start()

        import app.config as config
        import app.models as models
        import app.utils.db as db

        importlib.reload(config)
        importlib.reload(db)
        importlib.reload(models)
        importlib.reload(models.user)
        importlib.reload(models.summary)
        self.db = db

    def tearDown(self):
        self.env_patch.stop()
        import app.config as config
        import app.models as models
        import app.utils.db as db

        importlib.reload(config)
        importlib.reload(db)
        importlib.reload(models)
        importlib.reload(models.user)
        importlib.reload(models.summary)
        self.temp_dir.cleanup()

    def test_init_db_creates_users_table(self):
        self.db.init_db()
        from sqlalchemy import inspect

        inspector = inspect(self.db.engine)
        tables = inspector.get_table_names()
        self.assertIn("users", tables)
        self.assertIn("summaries", tables)


if __name__ == "__main__":
    unittest.main()
