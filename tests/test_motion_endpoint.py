import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import create_app


class TestMotionMjpg(unittest.TestCase):
    def setUp(self):
        self.login_patch = patch("app.routes.login_required", lambda x: x)
        self.login_patch.start()
        self.app = create_app(enable_watchdog=False, schedule=False, log_cache=False)
        self.client = self.app.test_client()
        self.app_context = self.app.app_context()
        self.app_context.push()

    def tearDown(self):
        self.login_patch.stop()
        self.app_context.pop()

    def _check_call(self, url, expected_camera, expected_group):
        with patch("app.routes.generate") as mock_gen:
            mock_gen.return_value = iter([b"TEST"])
            resp = self.client.get(url)
            self.assertEqual(resp.status_code, 200)
            mock_gen.assert_called_with(
                group=expected_group,
                camera=expected_camera,
                filename="last_motion.png",
            )
            next(resp.response)

    def test_camera_query(self):
        self._check_call("/motion.mjpg?camera=cam1", "cam1", None)

    def test_group_query(self):
        self._check_call("/motion.mjpg?group=front", None, "front")


if __name__ == "__main__":
    unittest.main()
