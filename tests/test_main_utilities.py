import os
import signal
import unittest
from unittest.mock import MagicMock, call, patch

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
            "ffmpeg_version": "6.0",
            "ffmpeg_path": "/usr/bin/ffmpeg",
            "machine_hwaccel": True,
            "ffmpeg_hwaccel": True,
            "hwaccel_enabled": True,
            "gpu_support": True,
            "ffmpeg_gpu_enabled": True,
            "danger_mode": True,
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
            (
                "FFmpeg Version: %s (%s)",
                metrics["ffmpeg_version"],
                metrics["ffmpeg_path"],
            ),
            ("Machine HW Accel: %s", metrics["machine_hwaccel"]),
            ("FFmpeg HW Accel: %s", metrics["ffmpeg_hwaccel"]),
            ("HW Accel Enabled: %s", metrics["hwaccel_enabled"]),
            ("GPU Support: %s", metrics["gpu_support"]),
            ("FFmpeg GPU Enabled: %s", metrics["ffmpeg_gpu_enabled"]),
            ("Danger Mode: %s", metrics["danger_mode"]),
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

        main.shutdown_manager.cleanup()

        mock_shutdown.assert_called_once_with(wait=True)
        t1.join.assert_called_once_with(timeout=0.01)
        t2.join.assert_called_once_with(timeout=0.01)
        mock_output.assert_called_once()

    @patch("main._start_shutdown_deadline")
    @patch("main._shutdown_signaled", False)
    @patch("main.shutdown_manager.cleanup")
    @patch("main.sys.exit")
    @patch("main.time.sleep")
    def test_graceful_shutdown_exits(
        self, mock_sleep, mock_exit, mock_cleanup, mock_deadline
    ):
        main.graceful_shutdown(
            signal.SIGTERM if hasattr(signal, "SIGTERM") else 0, None
        )
        # Repeated signals must not extend the process exit deadline.
        main.graceful_shutdown(signal.SIGTERM, None)
        mock_cleanup.assert_called_once()
        mock_exit.assert_called_once_with(0)
        mock_deadline.assert_called_once()

    @patch("main.subprocess.run")
    def test_clear_console_windows(self, mock_run):
        with (
            patch.object(main.os, "name", "nt"),
            patch("main.sys.stdout.isatty", return_value=True),
        ):
            main.clear_console()
            mock_run.assert_called_once_with(
                ["cmd.exe", "/d", "/c", "cls"], check=False, timeout=2
            )

    @patch("main.subprocess.run")
    def test_clear_console_posix(self, mock_run):
        with (
            patch.object(main.os, "name", "posix"),
            patch("main.sys.stdout.isatty", return_value=True),
        ):
            main.clear_console()
            mock_run.assert_called_once_with(["clear"], check=False, timeout=2)

    @patch("main.subprocess.run")
    def test_clear_console_skips_redirected_output(self, mock_run):
        with patch("main.sys.stdout.isatty", return_value=False):
            main.clear_console()
        mock_run.assert_not_called()

    @patch("main.subprocess.run", side_effect=FileNotFoundError)
    def test_missing_clear_command_does_not_prevent_startup(self, mock_run):
        with patch("main.sys.stdout.isatty", return_value=True):
            main.clear_console()

    @patch("main.clear_console")
    def test_version_exits_before_startup(self, mock_clear):
        with self.assertRaises(SystemExit) as result:
            main.main(["--version"])
        self.assertEqual(result.exception.code, 0)
        mock_clear.assert_not_called()

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

    @patch("main.subprocess.run")
    def test_get_port_usage_lsof(self, mock_run):
        result = MagicMock(stdout="lsof output", stderr="")
        mock_run.return_value = result

        output = main.get_port_usage(8082)

        mock_run.assert_called_once_with(
            [
                "lsof",
                "-i",
                ":8082",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(output, "lsof output")

    @patch("main.subprocess.run")
    def test_get_port_usage_fuser_fallback(self, mock_run):
        result = MagicMock(stdout="fuser output", stderr="")
        mock_run.side_effect = [FileNotFoundError, result]

        output = main.get_port_usage(8082)

        expected_calls = [
            call(
                [
                    "lsof",
                    "-i",
                    ":8082",
                ],
                capture_output=True,
                text=True,
                check=False,
            ),
            call(
                [
                    "fuser",
                    "-n",
                    "tcp",
                    "8082",
                ],
                capture_output=True,
                text=True,
                check=False,
            ),
        ]
        self.assertEqual(mock_run.call_args_list, expected_calls)
        self.assertEqual(output, "fuser output")


if __name__ == "__main__":
    unittest.main()
