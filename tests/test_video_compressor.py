import unittest
import tempfile
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.utils.video_compressor import compress_and_cleanup


class TestVideoCompressor(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.test_video_path = os.path.join(self.temp_dir, "test_video.mp4")

        # Create a dummy video file
        with open(self.test_video_path, "wb") as f:
            f.write(b"dummy video content")

    def tearDown(self):
        if os.path.exists(self.test_video_path):
            os.remove(self.test_video_path)
        os.rmdir(self.temp_dir)

    def test_compress_and_cleanup(self):
        # Note: This test is a placeholder and will need to be updated
        # once the compress_and_cleanup function is implemented
        result = compress_and_cleanup()
        self.assertIsNone(result)  # Assuming the function returns None for now

    def test_compress_and_cleanup_file_exists(self):
        # This test checks if the function handles existing files correctly
        # It should be updated once the actual implementation is in place
        initial_size = os.path.getsize(self.test_video_path)
        compress_and_cleanup()
        self.assertTrue(os.path.exists(self.test_video_path))
        final_size = os.path.getsize(self.test_video_path)
        self.assertEqual(initial_size, final_size)  # Assuming no change for now


if __name__ == "__main__":
    unittest.main()
