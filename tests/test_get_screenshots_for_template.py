import os
import shutil
import unittest
from unittest.mock import patch

from app.utils.template_manager import get_screenshots_for_template  # noqa: E402


class TestGetScreenshotsForTemplate(unittest.TestCase):
    def setUp(self):
        self.test_dir = "test_sort_shots"
        self.base = os.path.join(self.test_dir, "cam1")
        os.makedirs(self.base, exist_ok=True)
        self.patch = patch(
            "app.utils.template_manager.SCREENSHOT_DIRECTORY", self.test_dir
        )
        self.patch.start()

        open(os.path.join(self.base, "cam1_20240101000000.png"), "wb").close()
        open(os.path.join(self.base, "cam1_20240102000000_blank.png"), "wb").close()
        open(os.path.join(self.base, "cam1_20240103000000.png"), "wb").close()

    def tearDown(self):
        self.patch.stop()
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_blank_suffix_sorted(self):
        shots = get_screenshots_for_template("cam1")
        self.assertEqual(
            shots,
            [
                "cam1_20240103000000.png",
                "cam1_20240102000000_blank.png",
                "cam1_20240101000000.png",
            ],
        )


if __name__ == "__main__":
    unittest.main()
