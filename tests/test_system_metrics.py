import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.utils import system_metrics


class TestFFmpegSupportCaching(unittest.TestCase):
    def setUp(self):
        system_metrics.FFMPEG_GPU_SUPPORT = None

    def tearDown(self):
        system_metrics.FFMPEG_GPU_SUPPORT = None

    def test_ffmpeg_supports_hwaccel_caches_result(self):
        output = b"Hardware acceleration methods:\nvaapi"
        with patch(
            "app.utils.system_metrics.subprocess.check_output", return_value=output
        ) as mock_check:
            self.assertTrue(system_metrics.ffmpeg_supports_hwaccel())
            self.assertTrue(system_metrics.ffmpeg_supports_hwaccel())
            self.assertEqual(mock_check.call_count, 1)

    @patch("app.utils.system_metrics.FFMPEG_HWACCEL", "cuda")
    @patch("app.utils.system_metrics.shutil.which", return_value="/usr/bin/ffmpeg")
    @patch("app.utils.system_metrics.machine_supports_hwaccel", return_value=True)
    @patch.object(system_metrics, "FFMPEG_VERSION", "6.0")
    def test_get_system_metrics_uses_cached_value(self, *_):
        with patch("app.utils.system_metrics.psutil") as mock_psutil:
            mock_psutil.disk_usage.return_value = SimpleNamespace(percent=55.5)
            process = mock_psutil.Process.return_value
            if hasattr(process, "num_fds"):
                process.num_fds.return_value = 3
            else:
                process.open_files.return_value = [1, 2, 3]

            with patch(
                "app.utils.system_metrics.subprocess.check_output",
                return_value=b"Hardware acceleration methods:\nvaapi",
            ) as mock_check:
                system_metrics.FFMPEG_GPU_SUPPORT = None
                metrics1 = system_metrics.get_system_metrics()
                metrics2 = system_metrics.get_system_metrics()
                call_count = mock_check.call_count

        self.assertTrue(metrics1["ffmpeg_hwaccel"])
        self.assertTrue(metrics2["ffmpeg_hwaccel"])
        self.assertEqual(call_count, 1)


if __name__ == "__main__":
    unittest.main()


def test_collector_attributes_native_threads_and_fresh_child_objects():
    from unittest.mock import Mock

    children = []
    for created, total in [(10, 1), (10, 3), (20, 100)]:
        child = Mock(pid=200)
        child.create_time.return_value = created
        child.cpu_times.return_value = SimpleNamespace(user=total, system=0)
        child.cmdline.return_value = ["/usr/bin/chrome"]
        children.append([child])
    proc = Mock()
    proc.children.side_effect = children
    proc.threads.side_effect = [
        [SimpleNamespace(id=100, user_time=t, system_time=0)] for t in (1, 2, 3)
    ]
    snapshots = []
    stop = Mock()
    stop.is_set.side_effect = [False, False, False, True]
    stop.wait.side_effect = lambda _: snapshots.append(
        list(system_metrics.system_metrics["top_threads"])
    )
    with (
        patch.object(system_metrics, "stop_event", stop),
        patch.object(system_metrics, "system_metrics", {}),
        patch.object(system_metrics, "thread_cpu_times", {}),
        patch.object(system_metrics, "child_cpu_times", {}),
        patch.object(system_metrics, "last_thread_sample", 0),
        patch.object(system_metrics.time, "monotonic", side_effect=[0, 1, 2, 3]),
        patch.object(system_metrics.psutil, "Process", return_value=proc),
        patch.object(system_metrics.psutil, "cpu_count", return_value=4),
        patch.object(system_metrics.psutil, "cpu_percent", return_value=50),
        patch.object(
            system_metrics.psutil,
            "virtual_memory",
            return_value=SimpleNamespace(percent=20),
        ),
        patch.object(
            system_metrics.threading,
            "enumerate",
            return_value=[
                SimpleNamespace(native_id=100, ident=9999, name="capture-worker")
            ],
        ),
    ):
        system_metrics.collect_system_metrics()
    assert snapshots[0] == [{"id": 100, "name": "capture-worker", "cpu": 0.0}]
    assert snapshots[1] == [
        {"id": 200, "name": "chrome", "cpu": 50.0},
        {"id": 100, "name": "capture-worker", "cpu": 25.0},
    ]
    # A new process reusing PID 200 must not inherit the old process's CPU.
    assert snapshots[2] == [{"id": 100, "name": "capture-worker", "cpu": 25.0}]
