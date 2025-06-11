import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from flask import Flask

from app.routes import init_routes


class TestProfiling(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        # disable authentication
        self.login_patch = patch("app.routes.login_required", lambda x: x)
        self.login_patch.start()
        # use temporary file for log
        self.temp_log = tempfile.NamedTemporaryFile(delete=False)
        self.log_patch = patch("app.utils.profiling.LOG_PATH", self.temp_log.name)
        self.log_patch.start()
        init_routes(self.app)
        self.client = self.app.test_client()

    def tearDown(self):
        self.login_patch.stop()
        self.log_patch.stop()
        self.temp_log.close()
        os.unlink(self.temp_log.name)

    def test_latency_recorded(self):
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        with open(self.temp_log.name) as f:
            data = json.load(f)
        self.assertTrue(any(d["route"] == "/health" for d in data))

    def test_baseline_update(self):
        self.client.get("/health")
        import scripts.update_latency_baseline as updater

        with tempfile.NamedTemporaryFile(delete=False) as temp_baseline:
            baseline_patch = patch.object(updater, "BASELINE_PATH", temp_baseline.name)
            with baseline_patch:
                updater.main()
            temp_baseline.close()
            with open(temp_baseline.name) as f:
                stats = json.load(f)
        os.unlink(temp_baseline.name)
        self.assertIn("/health", stats)


if __name__ == "__main__":
    unittest.main()
