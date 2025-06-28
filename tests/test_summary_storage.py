import importlib
import os
import tempfile
import unittest
from unittest.mock import patch

import app.config as config
import app.utils.db as db
import app.utils.scheduling as scheduling
from app.models import Summary


class TestSummaryStorage(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test.db")
        self.env_patch = patch.dict(
            os.environ, {"GLIMPSER_DATABASE_PATH": self.db_path}
        )
        self.env_patch.start()

        importlib.reload(config)
        importlib.reload(db)
        importlib.reload(scheduling)
        import app.models as models

        importlib.reload(models)
        importlib.reload(models.summary)
        db.init_db()

    def tearDown(self):
        self.env_patch.stop()
        importlib.reload(config)
        importlib.reload(db)
        importlib.reload(scheduling)
        import app.models as models

        importlib.reload(models)
        importlib.reload(models.summary)
        self.temp_dir.cleanup()

    @patch(
        "app.utils.scheduling.get_templates_sorted_by_last_caption_time",
        return_value=[],
    )
    @patch("app.utils.scheduling.summarize", return_value='{"1":"foo"}')
    def test_update_summary_saves_to_db(self, mock_sum, mock_get_templates):
        scheduling.update_summary()
        session = db.SessionLocal()
        try:
            rows = session.query(Summary).all()
            self.assertGreaterEqual(len(rows), 1)
        finally:
            session.close()
