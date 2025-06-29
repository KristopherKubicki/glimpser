"""Tests for clip refresh."""
import unittest
from unittest.mock import patch

from app.utils.scheduling import refresh_clips, schedule_clip_refresh


class TestClipRefresh(unittest.TestCase):
    @patch("app.utils.scheduling.os.listdir")
    @patch("app.utils.scheduling.validate_template_name", return_value=True)
    @patch("app.utils.scheduling.requests.get")
    def test_refresh_clips_makes_requests(self, mock_get, _validate, mock_listdir):
        mock_listdir.return_value = ["cam1", "cam2"]
        with (
            patch("app.utils.scheduling.VIDEO_DIRECTORY", "/video"),
            patch("app.utils.scheduling.PORT", 1234),
            patch("app.utils.scheduling.CLIP_REFRESH_MAX_CAMERAS", 10),
        ):
            refresh_clips()
        self.assertEqual(mock_get.call_count, 2)
        mock_get.assert_any_call("http://127.0.0.1:1234/clip/cam1", timeout=5)
        mock_get.assert_any_call("http://127.0.0.1:1234/clip/cam2", timeout=5)

    @patch("app.utils.scheduling.os.listdir")
    @patch("app.utils.scheduling.validate_template_name", return_value=True)
    @patch("app.utils.scheduling.requests.get")
    def test_refresh_clips_skips_when_over_limit(
        self, mock_get, _validate, mock_listdir
    ):
        mock_listdir.return_value = ["cam1", "cam2", "cam3"]
        with (
            patch("app.utils.scheduling.VIDEO_DIRECTORY", "/video"),
            patch("app.utils.scheduling.PORT", 1234),
            patch("app.utils.scheduling.CLIP_REFRESH_MAX_CAMERAS", 2),
            self.assertLogs(level="INFO") as logs,
        ):
            refresh_clips()
        mock_get.assert_not_called()
        self.assertIn("Skipping clip refresh", " ".join(logs.output))


class TestScheduleClipRefresh(unittest.TestCase):
    @patch("app.utils.scheduling.scheduler.add_job")
    def test_schedule_clip_refresh_params(self, mock_add_job):
        schedule_clip_refresh()
        mock_add_job.assert_called_once_with(
            func=refresh_clips,
            trigger="interval",
            minutes=5,
            id="refresh_clips",
            replace_existing=True,
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
