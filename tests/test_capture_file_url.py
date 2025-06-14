import os
import sys
import tempfile
import unittest
from unittest.mock import patch

import app.utils.screenshots as ss


class TestCaptureFileURL(unittest.TestCase):
    @patch("app.utils.screenshots.download_image", return_value=True)
    @patch("app.utils.screenshots.is_address_reachable")
    def test_file_url_does_not_call_reachable(self, mock_reachable, mock_download):
        mock_reachable.side_effect = AssertionError("should not be called")
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            path = tmp.name
        try:
            url = f"file://{path}"
            result = ss.capture_or_download("test", {"url": url})
            self.assertFalse(result)
            mock_download.assert_not_called()
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()
