import unittest
import tempfile
import os
from unittest.mock import patch, MagicMock

from app.utils.screenshots import capture_screenshot_and_har_light


class TestScreenshotLight(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.output_path = os.path.join(self.temp_dir, "test screenshot.png")

    def tearDown(self):
        if os.path.exists(self.output_path):
            os.remove(self.output_path)
        os.rmdir(self.temp_dir)

    def test_subprocess_run_receives_unquoted_args(self):
        url = "http://example.com/test path"
        tmp_path = self.output_path.replace(".png", ".tmp.png")
        mock_image = MagicMock()
        mock_image.convert.return_value = mock_image
        with (
            patch(
                "app.utils.screenshots.shutil.which",
                return_value="/usr/bin/wkhtmltoimage",
            ),
            patch("app.utils.screenshots.subprocess.run") as mock_run,
            patch("app.utils.screenshots.os.path.exists", return_value=True),
            patch("app.utils.screenshots._is_valid_png", return_value=True),
            patch("app.utils.screenshots.Image.open") as mock_open,
            patch("app.utils.screenshots.is_mostly_blank", return_value=False),
            patch("app.utils.screenshots.remove_background", return_value=mock_image),
            patch("app.utils.screenshots.apply_dark_mode", return_value=mock_image),
            patch("app.utils.screenshots.add_timestamp"),
            patch("app.utils.screenshots.os.rename"),
        ):
            mock_open.return_value.__enter__.return_value = mock_image
            mock_open.return_value.__exit__.return_value = None
            mock_run.return_value.returncode = 0
            capture_screenshot_and_har_light(url, self.output_path)

        command = mock_run.call_args.args[0]
        self.assertEqual(command[-2], url)
        self.assertEqual(command[-1], tmp_path)

    def test_valid_tmp_png_saved(self):
        url = "http://example.com"
        tmp_path = self.output_path.replace(".png", ".tmp.png")
        mock_image = MagicMock()
        mock_image.convert.return_value = mock_image
        with (
            patch(
                "app.utils.screenshots.shutil.which",
                return_value="/usr/bin/wkhtmltoimage",
            ),
            patch("app.utils.screenshots.subprocess.run") as mock_run,
            patch("app.utils.screenshots.os.path.exists", return_value=True),
            patch(
                "app.utils.screenshots._is_valid_png", return_value=True
            ) as mock_valid,
            patch("app.utils.screenshots.Image.open") as mock_open,
            patch("app.utils.screenshots.is_mostly_blank", return_value=False),
            patch("app.utils.screenshots.remove_background", return_value=mock_image),
            patch("app.utils.screenshots.apply_dark_mode", return_value=mock_image),
            patch("app.utils.screenshots.add_timestamp"),
            patch("app.utils.screenshots.os.rename") as mock_rename,
        ):
            mock_open.return_value.__enter__.return_value = mock_image
            mock_open.return_value.__exit__.return_value = None
            mock_run.return_value.returncode = 0
            result = capture_screenshot_and_har_light(url, self.output_path)

        mock_valid.assert_called_once_with(tmp_path)
        mock_rename.assert_called_once_with(tmp_path, self.output_path)
        self.assertTrue(result)


if __name__ == "__main__":
    unittest.main()
