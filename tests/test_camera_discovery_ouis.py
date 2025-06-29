"""Tests for camera discovery ouis."""
import os
import tempfile
import unittest
from unittest.mock import patch

from app.utils import camera_discovery


class TestLoadLocalOuis(unittest.TestCase):
    def test_load_local_ouis_parsing(self):
        with tempfile.NamedTemporaryFile("w", delete=False) as tmp:
            tmp.write(
                "# comment\n"
                "00:11:22 SomeVendor\n"
                "33-44-55 AnotherVendor\n"
                "0044 invalid\n"
                "malformed\n"
                "aa:bb:cc:dd:ee AnotherOne\n"
            )
            path = tmp.name
        try:
            with patch.object(camera_discovery, "_OUI_FILES", [path, "/nonexistent"]):
                vendors = camera_discovery._load_local_ouis()
            expected = {
                "001122": "SomeVendor",
                "334455": "AnotherVendor",
                "aabbcc": "AnotherOne",
            }
            self.assertEqual(vendors, expected)
        finally:
            os.unlink(path)

    def test_load_local_ouis_missing_file(self):
        with patch.object(camera_discovery, "_OUI_FILES", ["/does/not/exist"]):
            vendors = camera_discovery._load_local_ouis()
        self.assertEqual(vendors, {})


if __name__ == "__main__":
    unittest.main()
