import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.utils import camera_fix


class TestCameraFix(unittest.TestCase):
    @patch("app.utils.camera_fix.camera_discovery.discover_cameras")
    @patch("app.utils.camera_fix.requests.get")
    def test_check_camera_template_success(self, mock_get, mock_discover):
        mock_discover.return_value = []
        mock_get.return_value = SimpleNamespace(
            ok=True, content=b"<html><div id='a'></div></html>", status_code=200
        )
        res = camera_fix.check_camera_template("http://x", [".//div[@id='a']"])
        self.assertTrue(res["valid_url"])
        self.assertTrue(res["xpath_results"][".//div[@id='a']"])
        mock_discover.assert_not_called()

    @patch("app.utils.camera_fix.camera_discovery.discover_cameras")
    @patch("app.utils.camera_fix.requests.get", side_effect=Exception("fail"))
    def test_check_camera_template_discovery(self, mock_get, mock_discover):
        mock_discover.return_value = [
            {"ip": "1.2.3.4", "protocol": "http", "port": 80, "info": {"path": "/"}}
        ]
        res = camera_fix.check_camera_template("http://x", [])
        self.assertFalse(res["valid_url"])
        self.assertTrue(res["suggestions"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
