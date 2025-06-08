import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.utils import camera_discovery


class TestTraceUpstream(unittest.TestCase):
    @patch("app.utils.camera_discovery.subprocess.run")
    @patch("app.utils.camera_discovery.shutil.which")
    def test_trace_upstream_success(self, mock_which, mock_run):
        def fake_which(cmd):
            return "/usr/bin/traceroute" if cmd == "traceroute" else None

        mock_which.side_effect = fake_which
        mock_run.return_value = SimpleNamespace(
            stdout="traceroute to 1.2.3.4\n1  192.168.1.1  1.123 ms\n"
        )
        hop = camera_discovery._trace_upstream("1.2.3.4")
        self.assertEqual(hop, "192.168.1.1")

    @patch(
        "app.utils.camera_discovery.subprocess.run",
        side_effect=RuntimeError("fail"),
    )
    @patch(
        "app.utils.camera_discovery.shutil.which", return_value="/usr/bin/traceroute"
    )
    def test_trace_upstream_error(self, mock_which, mock_run):
        hop = camera_discovery._trace_upstream("1.2.3.4")
        self.assertIsNone(hop)


if __name__ == "__main__":
    unittest.main()
