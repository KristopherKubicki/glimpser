import unittest
import unittest.mock
from unittest.mock import MagicMock, patch

from app.utils.api_utils import request_with_retry


class TestRequestWithRetry(unittest.TestCase):
    def test_success_first_try(self):
        resp = MagicMock()
        with patch(
            "app.utils.api_utils.requests.request", return_value=resp
        ) as mock_req:
            result = request_with_retry("get", "http://ex")
            self.assertIs(result, resp)
            mock_req.assert_called_once_with(
                "get", "http://ex", timeout=30, proxies={"http": None, "https": None}
            )

    def test_retry_then_success(self):
        resp = MagicMock()
        with (
            patch(
                "app.utils.api_utils.requests.request",
                side_effect=[Exception("fail"), resp],
            ) as mock_req,
            patch("time.sleep") as mock_sleep,
        ):
            result = request_with_retry("get", "http://ex", retries=1, backoff_factor=0)
            self.assertIs(result, resp)
            self.assertEqual(mock_req.call_count, 2)
            calls = [
                unittest.mock.call(
                    "get",
                    "http://ex",
                    timeout=30,
                    proxies={"http": None, "https": None},
                ),
                unittest.mock.call(
                    "get",
                    "http://ex",
                    timeout=30,
                    proxies={"http": None, "https": None},
                ),
            ]
            mock_req.assert_has_calls(calls)
            mock_sleep.assert_called_once()

    def test_retry_exhausted_raises(self):
        with (
            patch(
                "app.utils.api_utils.requests.request", side_effect=Exception("fail")
            ) as mock_req,
            patch("time.sleep"),
        ):
            with self.assertRaises(Exception):
                request_with_retry("get", "http://ex", retries=1, backoff_factor=0)
            self.assertEqual(mock_req.call_count, 2)


if __name__ == "__main__":
    unittest.main()
