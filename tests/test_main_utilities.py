import sys
import os
import unittest
import signal
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import main  # noqa: E402


class TestMainUtilities(unittest.TestCase):
    @patch("main.logging.info")
    @patch("main.get_system_metrics")
    def test_output_shutdown_stats_logs_metrics(self, mock_metrics, mock_log):
        metrics = {
            "cpu_usage": 10,
            "memory_usage": 20,
            "disk_usage": 30,
            "open_files": 40,
            "thread_count": 5,
            "uptime": "1h",
        }
        mock_metrics.return_value = metrics

        main.output_shutdown_stats()

        expected = [
            ("System Metrics at Shutdown:",),
            ("CPU Usage: %s%%", metrics["cpu_usage"]),
            ("Memory Usage: %s%%", metrics["memory_usage"]),
            ("Disk Usage: %s%%", metrics["disk_usage"]),
            ("Open Files: %s", metrics["open_files"]),
            ("Thread Count: %s", metrics["thread_count"]),
            ("Uptime: %s", metrics["uptime"]),
            ("Thank you for running Glimpser. Goodbye!",),
        ]
        self.assertEqual([c.args for c in mock_log.call_args_list], expected)

    @patch("main.output_shutdown_stats")
    @patch("main.threading.current_thread")
    @patch("main.threading.enumerate")
    @patch("main.scheduler.shutdown")
    @patch("main.time.sleep")
    def test_cleanup_resources_joins_threads(
        self, mock_sleep, mock_shutdown, mock_enumerate, mock_current, mock_output
    ):
        current = MagicMock()
        mock_current.return_value = current
        t1 = MagicMock()
        t2 = MagicMock()
        mock_enumerate.return_value = [current, t1, t2]

        main.cleanup_resources()

        mock_shutdown.assert_called_once_with(wait=True)
        t1.join.assert_called_once_with(timeout=0.01)
        t2.join.assert_called_once_with(timeout=0.01)
        mock_output.assert_called_once()

    @patch("main.sys.exit")
    @patch("main.time.sleep")
    def test_graceful_shutdown_exits(self, mock_sleep, mock_exit):
        main.graceful_shutdown(
            signal.SIGTERM if hasattr(signal, "SIGTERM") else 0, None
        )
        mock_exit.assert_called_once_with(0)

    @patch("main.os.system")
    def test_clear_console_windows(self, mock_system):
        with patch.object(main.os, "name", "nt"):
            main.clear_console()
            mock_system.assert_called_once_with("cls")

    @patch("main.os.system")
    def test_clear_console_posix(self, mock_system):
        with patch.object(main.os, "name", "posix"):
            main.clear_console()
            mock_system.assert_called_once_with("clear")

    @patch("main.clear_console")
    def test_clear_console_cli_calls_clear(self, mock_clear):
        main.clear_console_cli()
        mock_clear.assert_called_once()

    @patch("main.socket.socket")
    def test_is_port_in_use(self, mock_socket):
        mock_instance = mock_socket.return_value.__enter__.return_value
        mock_instance.connect_ex.side_effect = [0, 1]

        self.assertTrue(main.is_port_in_use(1234))
        self.assertFalse(main.is_port_in_use(5678))

    @patch("main.socket.socket")
    def test_is_port_in_use_docker(self, mock_socket):
        os.environ["IN_DOCKER"] = "1"
        try:
            self.assertFalse(main.is_port_in_use(1234))
            mock_socket.assert_not_called()
        finally:
            os.environ.pop("IN_DOCKER")


if __name__ == "__main__":
    unittest.main()
