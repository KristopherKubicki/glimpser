import os
import socket
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.utils.screenshots import is_chrome_debug_port_open


class TestChromeDebugPort(unittest.TestCase):
    def test_detect_open_and_closed_port(self):
        server = socket.socket()
        server.bind(("127.0.0.1", 0))
        port = server.getsockname()[1]
        server.listen(1)
        try:
            self.assertTrue(is_chrome_debug_port_open("127.0.0.1", port, timeout=1))
        finally:
            server.close()
        self.assertFalse(is_chrome_debug_port_open("127.0.0.1", port, timeout=1))


if __name__ == "__main__":
    unittest.main()
