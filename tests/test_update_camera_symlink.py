import os
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

import app.utils.scheduling as scheduling


class TestUpdateCameraSymlink(unittest.TestCase):
    def test_handles_relative_prev_motion_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            cam_dir = os.path.join(tmp, "cam1")
            os.makedirs(cam_dir)
            img1 = os.path.join(cam_dir, "img1.png")
            img2 = os.path.join(cam_dir, "img2.png")
            Image.new("RGB", (10, 10)).save(img1)
            Image.new("RGB", (10, 10)).save(img2)

            os.symlink("img1.png", os.path.join(cam_dir, "last_motion.png"))

            template = {"name": "cam1", "motion": 0, "last_caption": "", "url": ""}

            with (
                patch("app.utils.scheduling.SCREENSHOT_DIRECTORY", tmp),
                patch("app.utils.scheduling.capture_or_download", return_value=True),
                patch("app.utils.scheduling.add_timestamp"),
                patch("app.utils.scheduling.remove_background"),
                patch("app.utils.scheduling.add_motion_and_caption"),
                patch("app.utils.scheduling.save_template"),
                patch("app.utils.scheduling.send_http_callback"),
                patch("app.utils.scheduling.chatgpt_compare", return_value="cap"),
                patch("app.utils.scheduling.is_mostly_blank", return_value=False),
                patch("app.utils.scheduling.get_template", return_value=template),
            ):
                scheduling.update_camera("cam1", template)

            self.assertTrue(os.path.islink(os.path.join(cam_dir, "prev_motion.png")))


if __name__ == "__main__":
    unittest.main()
