import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.config import _detect_best_encoder


class TestDetectBestEncoder(unittest.TestCase):
    def test_detects_cuda(self):
        sample = "Encoders:\n V..... h264_nvenc"
        with patch("app.config.subprocess.check_output", return_value=sample.encode()):
            self.assertEqual(_detect_best_encoder(), "cuda")

    def test_returns_false_when_none(self):
        with patch("app.config.subprocess.check_output", return_value=b""):
            self.assertEqual(_detect_best_encoder(), "false")


if __name__ == "__main__":
    unittest.main()
