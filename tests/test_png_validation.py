# tests/test_png_validation.py

import unittest
import tempfile
import os
import sys
from PIL import Image

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.utils.screenshots import _is_valid_png


class TestPNGValidation(unittest.TestCase):
    def test_valid_png(self):
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            path = tmp.name
        try:
            with Image.new("RGB", (10, 10), color="red") as img:
                img.save(path)
            self.assertTrue(_is_valid_png(path))
        finally:
            os.remove(path)

    def test_invalid_png(self):
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            path = tmp.name
        try:
            # create an empty file
            with open(path, "wb") as f:
                f.write(b"")
            self.assertFalse(_is_valid_png(path))
        finally:
            os.remove(path)


if __name__ == "__main__":
    unittest.main()
