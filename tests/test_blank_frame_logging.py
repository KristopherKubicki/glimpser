import os
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

from app.utils import scheduling


class TestBlankFrameLogging(unittest.TestCase):
    def test_blank_frame_logs_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            cam_dir = os.path.join(tmp, "cam1")
            os.makedirs(cam_dir)
            shot = os.path.join(cam_dir, "cam1_20240101000000.png")
            Image.new("RGB", (10, 10)).save(shot)

            template = {"name": "cam1", "url": "http://example.com", "motion": 1}

            db_path = os.path.join(tmp, "test.db")
            with (
                patch.dict(os.environ, {"GLIMPSER_DATABASE_PATH": db_path}),
                patch("app.utils.scheduling.SCREENSHOT_DIRECTORY", tmp),
                patch("app.utils.scheduling.capture_or_download", return_value=True),
                patch("app.utils.scheduling.get_template", return_value=template),
                patch("app.utils.scheduling.is_mostly_blank", return_value=True),
                patch("app.utils.scheduling.os.symlink"),
                patch("app.utils.scheduling.os.rename"),
                patch("app.utils.scheduling.os.unlink"),
                patch("app.utils.scheduling.get_cached_status_code", return_value=404),
            ):
                with self.assertLogs(level="INFO") as logs:
                    scheduling.update_camera("cam1", template)

            joined = "\n".join(logs.output)
            self.assertIn("Skipping blank frame for motion detection", joined)
            self.assertIn("HTTP status: 404", joined)


if __name__ == "__main__":
    unittest.main()
