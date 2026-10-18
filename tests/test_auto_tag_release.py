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
            ["git", "tag", "-l", "v3.0.0"], capture_output=True, text=True, check=False
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

    def test_project_version_wins_over_tool_version_and_spacing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            pyproject = Path(tmpdir) / "pyproject.toml"
            pyproject.write_text(
                '[project]\nversion         = "0.2.10"\n'
                '[tool.commitizen]\nversion = "0.2.9"\n'
            )
            self.assertEqual(auto_tag_release.get_version(pyproject), "0.2.10")

    def test_missing_project_version_does_not_use_tool_version(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "pyproject.toml"
            path.write_text('[tool.commitizen]\nversion = "0.2.9"\n')
            with self.assertRaisesRegex(RuntimeError, "project.version"):
                auto_tag_release.get_version(path)

    def test_print_version_never_creates_or_pushes_tag(self):
        with (
            patch.object(auto_tag_release, "get_version", return_value="0.2.10"),
            patch.object(auto_tag_release, "create_tag") as create,
            patch("builtins.print") as output,
        ):
            auto_tag_release.main(["--print-version"])
            output.assert_called_once_with("0.2.10")
            create.assert_not_called()


if __name__ == "__main__":
    unittest.main()
