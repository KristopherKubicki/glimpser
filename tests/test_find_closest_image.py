import unittest
import tempfile
import os
import sys
from datetime import datetime
from PIL import Image

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.utils.scheduling import find_closest_image


class TestFindClosestImage(unittest.TestCase):
    def test_find_closest_image(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            times = [
                datetime(2023, 1, 1, 1, 1, 0),
                datetime(2023, 1, 1, 1, 2, 0),
                datetime(2023, 1, 1, 1, 5, 0),
            ]

            for t in times:
                filename = t.strftime("%Y%m%d%H%M%S") + "_motion.png"
                filepath = os.path.join(temp_dir, filename)
                Image.new("RGB", (1, 1)).save(filepath)

            last_caption_time = datetime(2023, 1, 1, 1, 3, 0)
            closest = find_closest_image(temp_dir, last_caption_time)

            expected = times[1].strftime("%Y%m%d%H%M%S") + "_motion.png"
            self.assertEqual(closest, expected)


if __name__ == "__main__":
    unittest.main()
