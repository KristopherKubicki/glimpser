import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.routes import file_location_metrics


class TestFileLocationMetrics(unittest.TestCase):
    def test_path_expansion_and_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = os.path.join(tmp, "home")
            envdir = os.path.join(tmp, "env")
            os.makedirs(home)
            os.makedirs(envdir)
            with patch.dict(os.environ, {"HOME": home, "TEST_DIR": envdir}):
                items = [
                    {"name": "home", "value": "~"},
                    {"name": "env", "value": "$TEST_DIR"},
                ]
                with patch("app.routes.psutil.disk_usage") as mock_usage:
                    mock_usage.return_value = SimpleNamespace(free=50, total=100)
                    result = file_location_metrics(items)

        self.assertIn("home", result)
        self.assertIn("env", result)
        for info in result.values():
            self.assertIn("exists", info)
            self.assertIn("free_pct", info)
            self.assertTrue(info["exists"])
            self.assertEqual(info["free_pct"], 50.0)

    def test_disk_usage_exception_sets_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            test_path = os.path.join(tmp, "file.txt")
            open(test_path, "w").close()
            items = [{"name": "file", "value": test_path}]
            with patch("app.routes.psutil.disk_usage", side_effect=Exception):
                result = file_location_metrics(items)
        self.assertIsNone(result["file"]["free_pct"])


if __name__ == "__main__":
    unittest.main()
