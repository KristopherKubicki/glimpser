import os
import sys
import unittest
from unittest.mock import patch

from flask import Flask

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.routes import init_routes


class TestCompileTeaserRoute(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.login_patch = patch("app.routes.login_required", lambda x: x)
        self.compile_patch = patch("app.routes.video_archiver.compile_to_teaser")
        self.throttle_patch = patch("app.utils.throttle._last_calls", {})
        self.login_patch.start()
        self.mock_compile = self.compile_patch.start()
        self.throttle_patch.start()
        init_routes(self.app)
        self.client = self.app.test_client()

    def tearDown(self):
        self.login_patch.stop()
        self.compile_patch.stop()
        self.throttle_patch.stop()

    def test_compile_teaser_post(self):
        resp = self.client.post("/compile_teaser")
        self.assertEqual(resp.status_code, 200)
        self.mock_compile.assert_called()

    def test_compile_teaser_get_not_allowed(self):
        resp = self.client.get("/compile_teaser")
        self.assertEqual(resp.status_code, 405)


if __name__ == "__main__":
    unittest.main()
