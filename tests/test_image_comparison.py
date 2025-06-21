import os
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

from app.utils.detect import calculate_difference_fast


class TestImageComparison(unittest.TestCase):
    def setUp(self):
        # Create two temporary image files for testing
        self.temp_dir = tempfile.mkdtemp()
        self.image_path_a = os.path.join(self.temp_dir, "image_a.png")
        self.image_path_b = os.path.join(self.temp_dir, "image_b.png")

        # Create a simple 100x100 black image
        image_a = Image.new("RGB", (100, 100), color="black")
        image_a.save(self.image_path_a)

        # Create a simple 100x100 white image
        image_b = Image.new("RGB", (100, 100), color="white")
        image_b.save(self.image_path_b)

    def tearDown(self):
        # Clean up temporary files
        os.remove(self.image_path_a)
        os.remove(self.image_path_b)
        os.rmdir(self.temp_dir)

    def test_calculate_difference_fast(self):
        # Test with two different images
        difference = calculate_difference_fast(self.image_path_a, self.image_path_b)
        self.assertAlmostEqual(difference, 1.0, places=2)

        # Test with the same image
        difference = calculate_difference_fast(self.image_path_a, self.image_path_a)
        self.assertAlmostEqual(difference, 0.0, places=2)

    def test_calculate_difference_fast_error(self):
        """Invalid paths should log an error and return ``None``."""
        with (
            patch("app.utils.detect.Image.open", side_effect=OSError),
            patch("app.utils.detect.logging.error") as mock_log,
        ):
            result = calculate_difference_fast("bad", "worse")
            self.assertIsNone(result)
            mock_log.assert_called_once()


if __name__ == "__main__":
    unittest.main()
