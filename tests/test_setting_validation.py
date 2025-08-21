import socket
import unittest

from app.utils.validators import MAX_WORKERS_MAX, validate_setting


class TestValidateSetting(unittest.TestCase):
    def test_valid_port(self):
        self.assertEqual(validate_setting("PORT", "8080"), "8080")

    def test_invalid_port_range(self):
        self.assertIsNone(validate_setting("PORT", "80"))

    def test_invalid_port_type(self):
        self.assertIsNone(validate_setting("PORT", "abc"))

    def test_unavailable_port(self):
        sock = socket.socket()
        sock.bind(("0.0.0.0", 0))
        port = sock.getsockname()[1]
        self.assertIsNone(validate_setting("PORT", str(port)))
        sock.close()

    def test_integer_setting(self):
        self.assertEqual(validate_setting("MAX_WORKERS", "4"), "4")
        self.assertIsNone(validate_setting("MAX_WORKERS", "bad"))

    def test_passthrough_unknown(self):
        self.assertEqual(validate_setting("CUSTOM", " value "), "value")

    def test_valid_tz(self):
        self.assertEqual(validate_setting("TZ", "UTC"), "UTC")

    def test_invalid_tz(self):
        self.assertIsNone(validate_setting("TZ", "Fake/Zone"))

    def test_valid_log_level(self):
        self.assertEqual(validate_setting("LOG_LEVEL", "debug"), "DEBUG")

    def test_invalid_log_level(self):
        self.assertIsNone(validate_setting("LOG_LEVEL", "VERBOSE"))

    def test_max_workers_limit(self):
        too_many = MAX_WORKERS_MAX + 1
        self.assertIsNone(validate_setting("MAX_WORKERS", str(too_many)))


if __name__ == "__main__":
    unittest.main()
