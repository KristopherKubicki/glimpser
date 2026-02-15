import json
import multiprocessing
import os
import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest.mock import ANY, patch

from PIL import Image

from app.utils import scheduling, system_metrics
from app.utils.scheduling import (
    add_motion_and_caption,
    process_offline_jobs,
    run_with_timeout,
    schedule_offline_job_processor,
)
from app.utils.system_metrics import get_system_metrics

dummy_log = []


def dummy_job(arg):
    """Helper function for offline job tests."""
    dummy_log.append(arg)


class TestRunWithTimeout(unittest.TestCase):
    def setUp(self):
        scheduling.active_jobs.clear()

    @patch("app.utils.scheduling.psutil.virtual_memory")
    @patch("app.utils.scheduling.psutil.cpu_percent", return_value=10)
    @patch("app.utils.scheduling.multiprocessing.Process")
    @patch("app.utils.scheduling.is_system_online", return_value=True)
    def test_run_completes_before_timeout(self, _online, mock_proc, _cpu, mock_mem):
        mock_mem.return_value.percent = 10
        flag = multiprocessing.Value("b", False)

        class DummyProc:
            def __init__(self, target=None, args=None, **_):
                self.target = target
                self.args = args or ()
                self.exitcode = 0

            def start(self):
                if self.target:
                    self.target(*self.args)

            def join(self, timeout=None):
                pass

            def is_alive(self):
                return False

            def terminate(self):
                pass

        mock_proc.side_effect = DummyProc

        def quick(val):
            val.value = True

        run_with_timeout(quick, args=(flag,), timeout=2)
        self.assertTrue(flag.value)

    @patch("app.utils.scheduling.is_system_online", return_value=True)
    @patch("time.sleep", return_value=None)
    @patch("app.utils.scheduling.multiprocessing.Process")
    def test_run_terminated_on_timeout(self, mock_proc, _sleep, _online):
        flag = multiprocessing.Value("b", False)

        class DummyProc:
            def __init__(self, *args, **kwargs):
                self.alive = False
                self.exitcode = 0

            def start(self):
                self.alive = True

            def join(self, timeout=None):
                if timeout is None:
                    self.alive = False

            def is_alive(self):
                return self.alive

            def terminate(self):
                self.alive = False

        mock_proc.side_effect = DummyProc

        def slow(val):
            time.sleep(1)
            val.value = True

        run_with_timeout(slow, args=(flag,), timeout=0.2)
        self.assertFalse(flag.value)

    @patch("app.utils.scheduling.psutil.cpu_percent", return_value=10)
    @patch("app.utils.scheduling.is_system_online", return_value=True)
    @patch("app.utils.scheduling.cas_error")
    @patch("app.utils.scheduling.mark_offline")
    @patch("time.sleep", return_value=None)
    @patch("app.utils.scheduling.multiprocessing.Process")
    def test_timeout_marks_offline(
        self, mock_proc, _sleep, mock_offline, mock_cas_error, _online, _cpu
    ):
        scheduling.active_jobs.clear()
        scheduling.job_backoff_until.clear()
        scheduling.job_failures.clear()

        class DummyProc:
            def __init__(self, *args, **kwargs):
                self.alive = False
                self.exitcode = 0

            def start(self):
                self.alive = True

            def join(self, timeout=None):
                if timeout is None:
                    self.alive = False

            def is_alive(self):
                return self.alive

            def terminate(self):
                self.alive = False

        mock_proc.side_effect = DummyProc

        def slow(name, template):
            time.sleep(1)

        run_with_timeout(
            slow,
            args=("cam1", {"url": "http://ex"}),
            timeout=0.2,
        )
        mock_offline.assert_called_once_with("cam1")
        mock_cas_error.assert_called_once_with("http://ex")

    @patch("app.utils.scheduling.is_system_online", return_value=True)
    def test_skip_if_active(self, _online):
        class DummyProc:
            def is_alive(self):
                return True

        scheduling.active_jobs["cam1"] = DummyProc()
        with patch("app.utils.scheduling.multiprocessing.Process") as mock_proc:
            run_with_timeout(lambda name: None, args=("cam1",), timeout=1)
            mock_proc.assert_not_called()

    @patch("app.utils.scheduling.psutil.cpu_percent", return_value=10)
    @patch("app.utils.scheduling.is_system_online", return_value=True)
    def test_backoff_on_failure(self, _online, _cpu):
        def bad_job():
            raise RuntimeError("boom")

        run_with_timeout(bad_job, timeout=1)
        backoff = scheduling.job_backoff_until.get("bad_job")
        self.assertIsNotNone(backoff)

        with patch("app.utils.scheduling.multiprocessing.Process") as mock_proc:
            run_with_timeout(bad_job, timeout=1)
            mock_proc.assert_not_called()

    @patch("app.utils.scheduling.psutil.cpu_percent", return_value=95)
    @patch("app.utils.scheduling.is_system_online", return_value=True)
    def test_skip_on_high_cpu(self, _online, _cpu):
        with patch("app.utils.scheduling.multiprocessing.Process") as mock_proc:
            run_with_timeout(lambda: None, timeout=1)
            mock_proc.assert_not_called()

    @patch("app.utils.scheduling.psutil.cpu_percent", return_value=10)
    @patch("app.utils.scheduling.is_system_online", return_value=True)
    def test_process_title_set(self, _online, _cpu):
        def my_job(name):
            return name

        scheduling.active_jobs.clear()
        scheduling.job_backoff_until.clear()
        scheduling.job_failures.clear()

        with patch("app.utils.scheduling.multiprocessing.Process") as mock_proc:
            run_with_timeout(my_job, args=("cam1",), timeout=1)
            mock_proc.assert_called_once()
            _, kwargs = mock_proc.call_args
            self.assertEqual(kwargs["name"], "glimpser my_job:cam1")

        scheduling.job_backoff_until.clear()
        scheduling.job_failures.clear()


class TestAddMotionAndCaption(unittest.TestCase):
    def test_image_updated_with_caption_and_motion(self):
        with unittest.mock.patch("app.utils.scheduling.DEBUG", False):
            with tempfile.TemporaryDirectory() as tmp:
                path = os.path.join(tmp, "test.png")
                Image.new("RGB", (50, 50), color="white").save(path)
                original = open(path, "rb").read()
                add_motion_and_caption(path, caption="hi", motion=True)
                updated = open(path, "rb").read()
                self.assertNotEqual(original, updated)
                Image.open(path).verify()


class TestSceneChangeGating(unittest.TestCase):
    def test_scene_signature_and_distance(self):
        with tempfile.TemporaryDirectory() as tmp:
            p1 = os.path.join(tmp, "a.png")
            p2 = os.path.join(tmp, "b.png")
            img1 = Image.new("RGB", (64, 64), color="black")
            img2 = Image.new("RGB", (64, 64), color="black")
            for x in range(8, 32):
                for y in range(8, 32):
                    img1.putpixel((x, y), (255, 255, 255))
            for x in range(32, 56):
                for y in range(32, 56):
                    img2.putpixel((x, y), (255, 255, 255))
            img1.save(p1)
            img2.save(p2)

            sig1 = scheduling._compute_scene_signature(p1)
            sig2 = scheduling._compute_scene_signature(p2)
            self.assertIsInstance(sig1, str)
            self.assertIsInstance(sig2, str)
            self.assertEqual(len(sig1), 16)
            self.assertEqual(len(sig2), 16)

            distance = scheduling._scene_hamming_distance(sig1, sig2)
            self.assertIsNotNone(distance)
            self.assertGreaterEqual(distance, 1)

    def test_scene_changed_threshold(self):
        changed, distance = scheduling._scene_changed("0" * 16, "0" * 16, threshold=1)
        self.assertFalse(changed)
        self.assertEqual(distance, 0)

        changed, distance = scheduling._scene_changed("0" * 16, "f" * 16, threshold=1)
        self.assertTrue(changed)
        self.assertIsNotNone(distance)
        self.assertGreater(distance, 0)


class TestSceneCaptionCache(unittest.TestCase):
    def test_scene_caption_cache_roundtrip_and_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_max = scheduling.SCENE_CAPTION_CACHE_MAX
            scheduling.SCENE_CAPTION_CACHE_MAX = 2
            try:
                scheduling._caption_cache_set(tmp, "sig1", "prompt", "caption-1")
                scheduling._caption_cache_set(tmp, "sig2", "prompt", "caption-2")
                scheduling._caption_cache_set(tmp, "sig3", "prompt", "caption-3")

                cache = scheduling._load_scene_caption_cache(tmp)
                self.assertEqual(len(cache), 2)
                self.assertNotIn(
                    "sig1:"
                    + scheduling.hashlib.sha1("prompt".encode()).hexdigest()[:12],
                    cache,
                )

                hit = scheduling._caption_cache_get(tmp, "sig3", "prompt")
                self.assertEqual(hit, "caption-3")
                miss = scheduling._caption_cache_get(tmp, "missing", "prompt")
                self.assertIsNone(miss)
            finally:
                scheduling.SCENE_CAPTION_CACHE_MAX = old_max


class TestGetSystemMetrics(unittest.TestCase):
    @patch("app.utils.system_metrics.psutil")
    @patch.object(system_metrics, "FFMPEG_VERSION", "6.0")
    @patch("app.utils.system_metrics.machine_supports_hwaccel", return_value=True)
    @patch("app.utils.system_metrics.ffmpeg_supports_hwaccel", return_value=True)
    @patch("app.utils.system_metrics.shutil.which", return_value="/usr/bin/ffmpeg")
    @patch("app.utils.system_metrics.FFMPEG_HWACCEL", "cuda")
    def test_metrics_fields(
        self,
        mock_which,
        mock_ffmpeg_supports,
        mock_machine,
        mock_psutil,
    ):
        # Ensure cached results don't leak between tests
        system_metrics.FFMPEG_GPU_SUPPORT = None
        scheduling.system_metrics.update(
            {
                "cpu_usage": 1.234,
                "memory_usage": 2.345,
                "thread_count": 5,
                "top_threads": [{"id": 123, "name": "Thread-1", "cpu": 10.0}],
                "start_time": time.time() - 3661,
            }
        )
        mock_psutil.disk_usage.return_value = SimpleNamespace(percent=55.5)
        process_mock = mock_psutil.Process.return_value
        if hasattr(process_mock, "num_fds"):
            process_mock.num_fds.return_value = 3
        else:
            process_mock.open_files.return_value = [1, 2, 3]
        metrics = get_system_metrics()
        self.assertEqual(metrics["cpu_usage"], 1.2)
        self.assertEqual(metrics["memory_usage"], 2.3)
        self.assertEqual(metrics["disk_usage"], 55.5)
        self.assertEqual(metrics["open_files"], 3)
        self.assertEqual(metrics["thread_count"], 5)
        self.assertTrue(metrics["uptime"].startswith("1h 1m"))
        self.assertEqual(metrics["ffmpeg_version"], "6.0")
        self.assertEqual(metrics["ffmpeg_path"], "/usr/bin/ffmpeg")
        self.assertTrue(metrics["machine_hwaccel"])
        self.assertTrue(metrics["ffmpeg_hwaccel"])
        self.assertTrue(metrics["ffmpeg_gpu_support"])
        self.assertTrue(metrics["hwaccel_enabled"])
        self.assertTrue(metrics["gpu_support"])
        self.assertTrue(metrics["ffmpeg_gpu_enabled"])
        self.assertTrue(metrics["danger_mode"])
        self.assertEqual(
            metrics["top_threads"], [{"id": 123, "name": "Thread-1", "cpu": 10.0}]
        )


class TestOfflineJobQueue(unittest.TestCase):
    def setUp(self):
        scheduling.active_jobs.clear()

    @patch("app.utils.scheduling.multiprocessing.Process")
    @patch("app.utils.scheduling.SessionLocal")
    @patch(
        "app.utils.scheduling.network_state",
        return_value={"wan_ok": True, "dns_ok": True},
    )
    @patch("app.utils.scheduling.is_system_online", return_value=False)
    def test_queue_created_when_offline(
        self, _online, _state, mock_session_local, mock_process
    ):
        class DummySession:
            def __init__(self):
                self.added = []
                self.committed = False

            def add(self, obj):
                self.added.append(obj)

            def commit(self):
                self.committed = True

            def rollback(self):
                pass

            def close(self):
                pass

        session = DummySession()
        mock_session_local.return_value = session

        run_with_timeout(lambda: None, timeout=1)

        self.assertEqual(len(session.added), 1)
        self.assertTrue(session.committed)
        mock_process.assert_not_called()

    @patch("app.utils.scheduling.is_system_online", return_value=True)
    @patch(
        "app.utils.scheduling.network_state",
        return_value={"wan_ok": True, "dns_ok": True},
    )
    @patch("app.utils.scheduling.SessionLocal")
    def test_process_runs_and_clears_jobs(self, mock_session_local, _state, _online):
        class DummyQuery:
            def __init__(self, session):
                self.session = session

            def order_by(self, *args, **kwargs):
                return self

            def all(self):
                return list(self.session.jobs)

        class DummySession:
            def __init__(self, jobs):
                self.jobs = jobs
                self.deleted = []

            def query(self, model):
                return DummyQuery(self)

            def delete(self, obj):
                self.deleted.append(obj)
                self.jobs.remove(obj)

            def commit(self):
                pass

            def rollback(self):
                pass

            def close(self):
                pass

        job = scheduling.OfflineJob(
            function="tests.test_scheduling_more.dummy_job",
            args=json.dumps(["ok"]),
            timeout=1,
            timestamp=0,
        )
        session = DummySession([job])
        mock_session_local.return_value = session

        with patch("app.utils.scheduling.run_with_timeout") as mock_run:
            process_offline_jobs()

        mock_run.assert_called_once()
        self.assertIn(job, session.deleted)


class TestSchedulerHealthTelemetry(unittest.TestCase):
    def setUp(self):
        with scheduling._scheduler_health_lock:  # noqa: SLF001
            scheduling._scheduler_max_instance_skips_total = 0  # noqa: SLF001
            scheduling._scheduler_last_max_instance_at = None  # noqa: SLF001
            scheduling._scheduler_job_max_instance_skips.clear()  # noqa: SLF001

    def test_tracks_max_instance_events(self):
        event = SimpleNamespace(
            code=scheduling.EVENT_JOB_MAX_INSTANCES,
            job_id="cam1",
        )
        scheduling.scheduler._track_job_state(event)  # noqa: SLF001

        health = scheduling.get_scheduler_health()
        self.assertEqual(health["max_instance_skips_total"], 1)
        self.assertEqual(health["top_skipped_jobs"][0]["job_id"], "cam1")
        self.assertEqual(health["top_skipped_jobs"][0]["count"], 1)


class TestCircuitBreaker(unittest.TestCase):
    def setUp(self):
        scheduling.active_jobs.clear()
        scheduling.job_failures.clear()
        scheduling.job_backoff_until.clear()
        scheduling.job_circuit_open_until.clear()
        scheduling.job_circuit_next_probe.clear()

    @patch("app.utils.scheduling.JOB_CIRCUIT_FAILURE_THRESHOLD", 3)
    @patch("app.utils.scheduling.JOB_CIRCUIT_COOLDOWN_SECONDS", 120)
    def test_register_job_failure_opens_circuit(self):
        scheduling.register_job_failure("cam1")
        scheduling.register_job_failure("cam1")
        scheduling.register_job_failure("cam1")

        self.assertEqual(scheduling.job_failures["cam1"], 3)
        self.assertGreater(
            scheduling.job_circuit_open_until.get("cam1", 0), time.time()
        )

    @patch("app.utils.scheduling.psutil.virtual_memory")
    @patch("app.utils.scheduling.psutil.cpu_percent", return_value=1)
    @patch("app.utils.scheduling.multiprocessing.Process")
    @patch("app.utils.scheduling.is_system_online", return_value=True)
    def test_run_with_timeout_skips_when_circuit_open(
        self, _online, mock_process, _cpu, mock_mem
    ):
        mock_mem.return_value.percent = 1
        scheduling.job_circuit_open_until["cam1"] = time.time() + 60

        scheduling.run_with_timeout(lambda *_a: None, args=("cam1",), timeout=1)

        mock_process.assert_not_called()

    @patch("app.utils.scheduling.psutil.virtual_memory")
    @patch("app.utils.scheduling.psutil.cpu_percent", return_value=1)
    @patch("app.utils.scheduling.multiprocessing.Process")
    @patch("app.utils.scheduling.is_system_online", return_value=True)
    def test_run_with_timeout_allows_half_open_probe(
        self, _online, mock_process, _cpu, mock_mem
    ):
        mock_mem.return_value.percent = 1

        class DummyProc:
            def __init__(self, *args, **kwargs):
                self.exitcode = 0

            def start(self):
                pass

            def join(self, timeout=None):
                pass

            def is_alive(self):
                return False

        mock_process.side_effect = DummyProc

        scheduling.job_circuit_open_until["cam1"] = time.time() + 60
        scheduling.job_circuit_next_probe["cam1"] = time.time() - 1

        scheduling.run_with_timeout(lambda *_a: None, args=("cam1",), timeout=1)

        mock_process.assert_called_once()


class TestOfflineJobScheduler(unittest.TestCase):
    @patch("app.utils.scheduling.scheduler.add_job")
    @patch("app.utils.scheduling.LOW_CPU_MODE", False)
    def test_schedule_offline_job_processor_default_interval(self, mock_add_job):
        schedule_offline_job_processor()
        mock_add_job.assert_called_once_with(
            func=ANY,
            trigger="interval",
            seconds=30,
            id="process_offline_jobs",
            replace_existing=True,
            max_instances=3,
            coalesce=True,
            misfire_grace_time=30,
        )
        self.assertEqual(
            mock_add_job.call_args.kwargs["func"].__name__, "process_offline_jobs"
        )

    @patch("app.utils.scheduling.scheduler.add_job")
    @patch("app.utils.scheduling.LOW_CPU_MODE", True)
    def test_schedule_offline_job_processor_low_cpu_interval(self, mock_add_job):
        schedule_offline_job_processor()
        mock_add_job.assert_called_once_with(
            func=ANY,
            trigger="interval",
            seconds=120,
            id="process_offline_jobs",
            replace_existing=True,
            max_instances=3,
            coalesce=True,
            misfire_grace_time=120,
        )
        self.assertEqual(
            mock_add_job.call_args.kwargs["func"].__name__, "process_offline_jobs"
        )


class TestLowCpuCrawlerScheduling(unittest.TestCase):
    @patch("app.utils.scheduling.LOW_CPU_MODE", True)
    @patch("app.utils.scheduling.get_templates")
    @patch("app.utils.scheduling.calculate_optimal_offsets", return_value={"cam1": 0})
    def test_low_cpu_clamps_short_intervals(self, _offsets, mock_get_templates):
        mock_get_templates.return_value = {"cam1": {"name": "cam1", "frequency": 1}}

        with patch("app.utils.scheduling.scheduler") as mock_scheduler:
            mock_scheduler.get_jobs.return_value = []
            scheduling.schedule_crawlers()

        camera_call = None
        for call in mock_scheduler.add_job.call_args_list:
            if call.kwargs.get("id") == "cam1":
                camera_call = call
                break

        self.assertIsNotNone(camera_call)
        self.assertEqual(camera_call.kwargs["seconds"], 120)


if __name__ == "__main__":
    unittest.main()
