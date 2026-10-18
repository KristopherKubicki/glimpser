import unittest
from unittest.mock import patch

from app import create_app


class TestTestMjpg(unittest.TestCase):
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
                filename="latest_camera.png",
            )
            next(resp.response)

    def test_invalid_filters_do_not_start_stream(self):
        with patch("app.routes.generate") as generate:
            for endpoint in ("/test.mjpg", "/stream.mjpg"):
                for field in ("camera", "group"):
                    response = self.client.get(
                        endpoint, query_string={field: "../outside"}
                    )
                    self.assertEqual(response.status_code, 400)
            generate.assert_not_called()

    def test_all_filters_remain_optional(self):
        self._check_call("/test.mjpg?camera=all&group=all", None, None)

    def test_camera_query(self):
        self._check_call("/test.mjpg?camera=cam1", "cam1", None)

    def test_group_query(self):
        self._check_call("/test.mjpg?group=front", None, "front")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
