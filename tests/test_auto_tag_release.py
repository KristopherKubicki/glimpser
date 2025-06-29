"""Tests for auto tag release."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from scripts import auto_tag_release  # noqa: E402


class TestAutoTagRelease(unittest.TestCase):
    def test_tag_exists_true_and_false(self):
        mock_run = MagicMock()
        mock_run.return_value.stdout = "v1.0.0\nv2.0.0\n"
        with patch("scripts.auto_tag_release.subprocess.run", mock_run):
            self.assertTrue(auto_tag_release.tag_exists("v1.0.0"))
            self.assertFalse(auto_tag_release.tag_exists("v3.0.0"))
        mock_run.assert_called_with(
            ["git", "tag", "-l", "v3.0.0"], capture_output=True, text=True
        )

    def test_create_tag_invokes_git_commands(self):
        with patch("scripts.auto_tag_release.subprocess.check_call") as mock_call:
            auto_tag_release.create_tag("v1.2.3")
            self.assertEqual(
                mock_call.call_args_list,
                [
                    unittest.mock.call(["git", "tag", "v1.2.3"]),
                    unittest.mock.call(["git", "push", "origin", "v1.2.3"]),
                ],
            )

    def test_get_version_parses_pyproject(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            pyproject = Path(tmpdir) / "pyproject.toml"
            pyproject.write_text('[project]\nversion = "9.9.9"\n')
            with patch.object(auto_tag_release, "VERSION_FILE", pyproject):
                self.assertEqual(auto_tag_release.get_version(), "9.9.9")


if __name__ == "__main__":
    unittest.main()
