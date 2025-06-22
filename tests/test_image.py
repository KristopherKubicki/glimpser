import os
import tempfile
import unittest

from PIL import Image

from app.utils.retention_policy import delete_old_files
from app.utils.screenshots import add_timestamp, is_mostly_blank, remove_background


class TestFileRetention(unittest.TestCase):

    def test_delete_old_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create some dummy files
            file_paths = []
            for i in range(5):
                file_path = os.path.join(temp_dir, f"file{i}.txt")
                with open(file_path, "w") as f:
                    f.write("Some content")
                os.utime(file_path, (i * 1000, i * 1000))  # Modify file creation time
                file_paths.append(file_path)

            # Test deletion when max_age is set to 0 (should delete all but the newest file)
            delete_old_files(file_paths, max_age=0, max_size=0, minimum=1)
            remaining_files = os.listdir(temp_dir)

            self.assertEqual(len(remaining_files), 1)


class TestImageProcessing(unittest.TestCase):

    def test_add_timestamp(self):
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as temp_file:
            image_path = temp_file.name

        try:
            # Create a simple image and add a timestamp
            with Image.new("RGB", (100, 100), color="black") as img:
                img.save(image_path)
            add_timestamp(image_path, name="Test Image", invert=False)
            self.assertTrue(os.path.exists(image_path))
        finally:
            os.remove(image_path)

    def test_remove_background(self):
        with Image.new("RGBA", (100, 100), color=(14, 14, 14, 255)) as img:
            for x in range(20, 80):
                for y in range(20, 80):
                    img.putpixel((x, y), (255, 0, 0, 255))
            result = remove_background(img)
            ratio = result.size[0] / result.size[1]
            self.assertAlmostEqual(ratio, 16 / 9, delta=0.15)

    def test_remove_background_white_border(self):
        with Image.new("RGBA", (100, 100), color=(255, 255, 255, 255)) as img:
            img.putpixel((50, 50), (0, 0, 0, 255))
            result = remove_background(img)
            self.assertIsInstance(result, Image.Image)

    def test_is_mostly_blank(self):
        with Image.new("RGB", (100, 100), color="white") as img:
            result = is_mostly_blank(img)
            self.assertTrue(result)

        with Image.new("RGB", (100, 100), color="black") as img:
            result = is_mostly_blank(img)
            self.assertTrue(result)

        with Image.new("RGB", (100, 100), color="white") as img:
            for x in range(0, 100):
                for y in range(0, 60):
                    img.putpixel((x, y), (0, 0, 0))
            result = is_mostly_blank(img)
            self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()
