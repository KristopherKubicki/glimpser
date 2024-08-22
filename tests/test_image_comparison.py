import unittest

from PIL import Image
import tempfile
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

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


if __name__ == "__main__":
    unittest.main()
