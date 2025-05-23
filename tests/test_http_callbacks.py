import unittest
from unittest.mock import patch

from app.utils.http_callbacks import send_http_callback


class TestHttpCallbacks(unittest.TestCase):
    def test_send_http_callback_no_url(self):
        with patch('requests.post') as mock_post:
            send_http_callback('', 'event', {})
            mock_post.assert_not_called()

    def test_send_http_callback_posts(self):
        with patch('requests.post') as mock_post:
            mock_post.return_value.status_code = 200
            send_http_callback('http://example.com', 'event', {'a': 1})
            mock_post.assert_called_once_with('http://example.com', json={'event': 'event', 'payload': {'a': 1}}, timeout=5)


if __name__ == '__main__':
    unittest.main()
