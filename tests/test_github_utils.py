import unittest
from unittest.mock import MagicMock, patch

from app.utils import github


class TestGithubUtils(unittest.TestCase):
    def test_update_available(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"tag_name": "v1.2.0"}
        with patch("app.utils.github.requests.get", return_value=mock_response):
            # Invalidate cache between calls
            github.get_latest_release_version.cache_clear()
            self.assertTrue(github.is_update_available("1.0.0"))

    def test_update_unavailable_on_error(self):
        with patch("app.utils.github.requests.get", side_effect=Exception("fail")):
            github.get_latest_release_version.cache_clear()
            self.assertFalse(github.is_update_available("1.0.0"))


if __name__ == "__main__":
    unittest.main()
