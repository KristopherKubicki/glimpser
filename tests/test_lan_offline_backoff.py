import time
import unittest
from unittest.mock import patch

from app.utils import scheduling


class TestLanOfflineBackoff(unittest.TestCase):
    def test_marks_offline_after_threshold(self):
        template = {"name": "cam1", "url": "http://192.168.1.10/image"}
        entry = {"reason": "lan_offline", "errors": 0, "first": time.time()}
        throttle = {template["url"]: entry}

        with (
            patch("app.utils.scheduling.throttle_cache", throttle),
            patch("app.utils.scheduling.get_template", return_value=template),
            patch("app.utils.scheduling.capture_or_download", return_value=False),
            patch("app.utils.scheduling.set_capture_failed"),
            patch("app.utils.scheduling.mark_offline") as mock_offline,
            patch("app.utils.scheduling.LAN_OFFLINE_DISABLE_ERRORS", 2),
            patch("app.utils.scheduling.LAN_OFFLINE_DISABLE_WINDOW_MINUTES", 60),
            patch("app.utils.scheduling.LAN_OFFLINE_BACKOFF_SECONDS", 10),
            patch("app.utils.scheduling.LOG_RATE_LIMIT_SEC", 0),
        ):
            scheduling.update_camera("cam1", template)
            scheduling.update_camera("cam1", template)

        mock_offline.assert_called_once_with("cam1")
        self.assertTrue(entry.get("lan_offline_marked"))


if __name__ == "__main__":
    unittest.main()
