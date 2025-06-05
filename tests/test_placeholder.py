import unittest
import tempfile
import os
from PIL import Image
from unittest.mock import patch

from app.utils.screenshots import create_placeholder, _finalize_screenshot


class TestPlaceholderGeneration(unittest.TestCase):
    def test_create_placeholder(self):
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            path = tmp.name
        try:
            create_placeholder(path, "Test")
            self.assertTrue(os.path.exists(path))
            with Image.open(path) as img:
                self.assertEqual(img.size, (640, 360))
        finally:
            os.remove(path)

    def test_finalize_blank_keeps_original(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = os.path.join(tmpdir, "tmp.png")
            final = os.path.join(tmpdir, "final.png")
            Image.new("RGB", (10, 10), color="black").save(tmp)
            with patch("app.utils.screenshots.is_mostly_blank", return_value=True):
                result = _finalize_screenshot(tmp, final, "Cam", False, False)
            self.assertFalse(result)
            self.assertTrue(os.path.exists(final))
            self.assertTrue(os.path.exists(final + ".orig.png"))


if __name__ == "__main__":
    unittest.main()
