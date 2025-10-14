import socket
import unittest

import pytest_socket

from app.utils.screenshots import is_chrome_debug_port_open


class TestChromeDebugPort(unittest.TestCase):
    def test_detect_open_and_closed_port(self):
        pytest_socket.enable_socket()
        server = socket.socket()
        server.bind(("127.0.0.1", 0))
        port = server.getsockname()[1]
        server.listen(1)
        try:
            self.assertTrue(is_chrome_debug_port_open("127.0.0.1", port, timeout=1))
        finally:
            server.close()
            pytest_socket.disable_socket()
        self.assertFalse(is_chrome_debug_port_open("127.0.0.1", port, timeout=1))


if __name__ == "__main__":
    unittest.main()
