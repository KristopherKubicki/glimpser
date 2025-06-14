import os
import shutil
import sys
import unittest
from unittest.mock import patch

from app.utils.template_manager import get_videos_for_template


class TestGetVideosForTemplate(unittest.TestCase):
    def setUp(self):
        self.test_dir = "test_sort_videos"
        self.base = os.path.join(self.test_dir, "cam1")
        os.makedirs(self.base, exist_ok=True)
        self.patch = patch("app.utils.template_manager.VIDEO_DIRECTORY", self.test_dir)
        self.patch.start()
        open(os.path.join(self.base, "final_1.mp4"), "wb").close()
        open(os.path.join(self.base, "final_10.mp4"), "wb").close()
        open(os.path.join(self.base, "final_2.mp4"), "wb").close()

    def tearDown(self):
        self.patch.stop()
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_numeric_sort_descending(self):
        videos = get_videos_for_template("cam1")
        self.assertEqual(
            videos,
            ["final_10.mp4", "final_2.mp4", "final_1.mp4", "last_video.mp4"],
        )


if __name__ == "__main__":
    unittest.main()
