import unittest
import os
import sys
from unittest.mock import patch, MagicMock
from requests.structures import CaseInsensitiveDict

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import app.utils.screenshots as ss


class TestHttpSession(unittest.TestCase):
    @patch("app.utils.screenshots.requests.Session")
    def test_http_session_singleton_and_headers(self, mock_session_cls):
        session_instance = MagicMock()
        session_instance.headers = CaseInsensitiveDict()
        mock_session_cls.return_value = session_instance

        ss._session = None

        sess1 = ss.http_session()
        sess2 = ss.http_session()

        self.assertIs(sess1, sess2)
        mock_session_cls.assert_called_once()
        self.assertIn("User-Agent", sess1.headers)
        self.assertIn("Accept", sess1.headers)


if __name__ == "__main__":
    unittest.main()
