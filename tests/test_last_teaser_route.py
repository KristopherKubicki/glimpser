import os
import sys
import unittest
from unittest.mock import patch

from flask import Flask

import app.config as config
import app.routes as routes
from app.routes import init_routes


class TestLastTeaserRoute(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.login_patch = patch("app.routes.login_required", lambda x: x)
        self.login_patch.start()
        init_routes(self.app)
        self.client = self.app.test_client()

    def tearDown(self):
        self.login_patch.stop()

    @patch("app.routes.send_file")
    @patch("os.path.exists", return_value=True)
    def test_last_teaser_group(self, mock_exists, mock_send):
        resp = self.client.get("/last_teaser?group=mygroup")
        self.assertEqual(resp.status_code, 200)
        expected = os.path.join(
            os.path.dirname(routes.__file__),
            "..",
            config.VIDEO_DIRECTORY,
            "mygroup_in_process.mp4",
        )
        mock_send.assert_called_with(expected)

    @patch("os.path.exists", return_value=True)
    def test_last_teaser_invalid_group(self, mock_exists):
        resp = self.client.get("/last_teaser?group=bad/name")
        self.assertEqual(resp.status_code, 400)


if __name__ == "__main__":
    unittest.main()
