# app/utils/scheduling.py

"""Manage Glimpser's background jobs and scheduler.

This module configures a :class:`GracefulAPScheduler` wrapper around
``APScheduler`` and provides helpers to run jobs in isolated processes with
backoff logic. Functions such as ``schedule_crawlers`` and
``schedule_summarization`` set up periodic crawling, summarization and other
maintenance tasks.
"""

import datetime
import hashlib
import importlib
import json
import logging
import multiprocessing
import os
import random
import re
import shutil
import sys
import threading
import time
from collections import OrderedDict
from functools import reduce
from math import gcd
from pathlib import Path

import psutil

try:
    from setproctitle import setproctitle
except Exception:  # pragma: no cover - optional dependency
    setproctitle = None
import numpy as np

try:  # prefer ONNX for lightweight deployments
    import onnxruntime as ort
except Exception:  # pragma: no cover - optional dependency
    ort = None

import requests
from apscheduler.events import (
    EVENT_JOB_ERROR,
    EVENT_JOB_EXECUTED,
    EVENT_JOB_MAX_INSTANCES,
    EVENT_JOB_SUBMITTED,
)
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from dateutil import parser
from flask_apscheduler import APScheduler
from PIL import Image, UnidentifiedImageError
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm.exc import ObjectDeletedError

from app.caption_policy import usable_caption
from app.config import (
    AUTO_UPDATE_BRANCH,
    CLIP_MODEL_NAME,
    CLIP_MODEL_PATH,
    CLIP_REFRESH_MAX_CAMERAS,
    CRAWLER_STARTUP_SPREAD,
)
from app.config import DEBUG as CONFIG_DEBUG
from app.config import (
    LAN_OFFLINE_BACKOFF_SECONDS,
    LAN_OFFLINE_DISABLE_ERRORS,
    LAN_OFFLINE_DISABLE_WINDOW_MINUTES,
    LOG_RATE_LIMIT_SEC,
    LOW_CPU_MODE,
    PORT,
    SCREENSHOT_DIRECTORY,
    SUMMARIES_DIRECTORY,
    VIDEO_DIRECTORY,
    WATCHDOG_CPU_THRESHOLD,
    WATCHDOG_MEMORY_THRESHOLD,
    get_setting,
)
from app.models import LogSummary, OfflineJob, Summary
from app.utils.auto_update import check_for_update
from app.utils.db import SessionLocal, ensure_column
from app.utils.logging_utils import sanitize_url

from . import browser_queue, camera_discovery
from . import system_metrics as _system_metrics
from .detect import calculate_difference_fast
from .email_alerts import email_alert
from .http_callbacks import send_http_callback
from .image_processing import _caption_cache_prompt, chatgpt_compare
from .image_utils import add_motion_and_caption, find_closest_image
from .llm import summarize
from .network import is_system_online, network_state
from .screenshots import (
    CAPTURE_STALE_BROWSER_SLOT_BUSY,
    CAPTURE_STALE_PREVIOUS,
    _is_valid_png,
    _postprocess_still_image,
    add_timestamp,
    capture_or_download,
    cas_error,
    check_user_activity,
    get_cached_status_code,
    is_chrome_debug_port_open,
    is_mostly_blank,
    is_stale_capture_result,
    throttle_cache,
)
from .sms_alerts import sms_alert
from .template_manager import (
    get_llm_cost_estimate,
    get_llm_response_count,
    get_screenshot_count,
    get_screenshots_for_template,
    get_storage_usage,
    get_storage_usage_bytes,
    get_template,
    get_templates,
    get_templates_sorted_by_last_caption_time,
    get_video_count,
    mark_offline,
    parse_canonical_screenshot_timestamp,
    save_caption_metadata,
    save_template,
    set_capture_failed,
    set_capture_stale,
    sort_canonical_screenshot_filenames,
    update_last_screenshot_time,
)
from .validators import validate_group_name, validate_template_name

# Precompile sentence boundary regex for efficiency
SENTENCE_SPLIT_RE = re.compile(r"\s*?(.+?[\?\!\.\,])(?: \s?|\t|$)", flags=re.DOTALL)
SUMMARY_MAX_LINES = 50

# Re-export select attributes for backwards compatibility with older tests.
LOGGING_PATH = _system_metrics.LOGGING_PATH
cache_logs = _system_metrics.cache_logs
start_log_caching = _system_metrics.start_log_caching
stop_background_tasks = _system_metrics.stop_background_tasks
system_metrics = _system_metrics.system_metrics
start_metrics_collection = _system_metrics.start_metrics_collection
stop_event = _system_metrics.stop_event
get_system_metrics = _system_metrics.get_system_metrics
log_cache = _system_metrics.log_cache
log_cache_lock = _system_metrics.log_cache_lock
DEBUG = CONFIG_DEBUG
CRAWLER_SCHEDULE_JITTER_SECONDS = max(
    0, int(os.getenv("CRAWLER_SCHEDULE_JITTER_SECONDS", "15"))
)
JOB_CIRCUIT_FAILURE_THRESHOLD = max(
    2, int(os.getenv("JOB_CIRCUIT_FAILURE_THRESHOLD", "6"))
)
JOB_CIRCUIT_COOLDOWN_SECONDS = max(
    30, int(os.getenv("JOB_CIRCUIT_COOLDOWN_SECONDS", "900"))
)
JOB_CIRCUIT_PROBE_SECONDS = max(30, int(os.getenv("JOB_CIRCUIT_PROBE_SECONDS", "120")))
SCENE_CAPTION_CACHE_MAX = max(1, int(os.getenv("SCENE_CAPTION_CACHE_MAX", "25")))


def _scene_caption_cache_path(directory: str) -> str:
    """Return path to per-camera scene caption cache file."""

    return os.path.join(directory, ".scene_caption_cache.json")


def _load_scene_caption_cache(directory: str) -> "OrderedDict[str, str]":
    """Load scene-signature caption cache for a camera directory."""

    path = _scene_caption_cache_path(directory)
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception:
        return OrderedDict()

    if not isinstance(data, dict):
        return OrderedDict()

    items: list[tuple[str, str]] = []
    for k, v in data.items():
        if isinstance(k, str) and isinstance(v, str) and k and v:
            items.append((k, v))
    if len(items) > SCENE_CAPTION_CACHE_MAX:
        items = items[-SCENE_CAPTION_CACHE_MAX:]
    return OrderedDict(items)


def _save_scene_caption_cache(directory: str, cache: "OrderedDict[str, str]") -> None:
    """Persist scene-signature caption cache atomically."""

    if not cache:
        return
    while len(cache) > SCENE_CAPTION_CACHE_MAX:
        cache.popitem(last=False)

    path = _scene_caption_cache_path(directory)
    tmp_path = f"{path}.tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as fh:
            json.dump(dict(cache), fh)
        os.replace(tmp_path, path)
    except Exception as exc:
        logging.debug("Unable to persist scene caption cache %s: %s", path, exc)
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass


def _scene_caption_cache_key(scene_signature: str, prompt: str) -> str:
    """Return a stable cache key combining scene signature and prompt."""

    prompt_hash = hashlib.sha256(
        _caption_cache_prompt(prompt).encode("utf-8", errors="ignore")
    ).hexdigest()[:24]
    return f"{scene_signature}:{prompt_hash}"


def _caption_cache_get(
    directory: str, scene_signature: str | None, prompt: str
) -> str | None:
    """Return cached caption for scene+prompt if present."""

    if not scene_signature:
        return None
    cache = _load_scene_caption_cache(directory)
    key = _scene_caption_cache_key(scene_signature, prompt)
    value = cache.get(key)
    if not value:
        return None
    # LRU touch
    cache.move_to_end(key)
    _save_scene_caption_cache(directory, cache)
    return value


def _caption_cache_set(
    directory: str, scene_signature: str | None, prompt: str, caption: str | None
) -> None:
    """Store caption for scene+prompt in per-camera LRU cache."""

    if not scene_signature or not caption:
        return
    cache = _load_scene_caption_cache(directory)
    key = _scene_caption_cache_key(scene_signature, prompt)
    cache[key] = caption
    cache.move_to_end(key)
    _save_scene_caption_cache(directory, cache)


def _compute_scene_signature(image_path: str, hash_size: int = 8) -> str | None:
    """Return a lightweight dHash-style signature for scene-change gating."""

    try:
        with Image.open(image_path) as img:
            resampling = getattr(Image, "Resampling", Image)
            gray = img.convert("L").resize(
                (hash_size + 1, hash_size), resampling.LANCZOS
            )
            pixels = list(gray.getdata())
        bits: list[int] = []
        row_width = hash_size + 1
        for row in range(hash_size):
            offset = row * row_width
            for col in range(hash_size):
                left = pixels[offset + col]
                right = pixels[offset + col + 1]
                bits.append(1 if left > right else 0)
        value = 0
        for bit in bits:
            value = (value << 1) | bit
        return f"{value:016x}"
    except Exception:
        return None


def _scene_hamming_distance(a: str, b: str) -> int | None:
    """Return Hamming distance between two same-size hex scene signatures."""

    if not a or not b or len(a) != len(b):
        return None
    try:
        return int((int(a, 16) ^ int(b, 16)).bit_count())
    except Exception:
        return None


def _scene_change_threshold(template: dict) -> int:
    """Return the scene-change threshold for caption triggering."""

    try:
        threshold = int(
            template.get("scene_change_hamming", get_setting("SCENE_CHANGE_HAMMING", 4))
        )
    except Exception:
        threshold = 4
    return max(1, threshold)


def _truthy_template_value(value) -> bool:
    """Return True for common truthy values stored by templates."""

    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _template_timestamp(value) -> datetime.datetime | None:
    """Parse a template timestamp as a naive UTC datetime."""

    if not value:
        return None
    try:
        parsed = datetime.datetime.strptime(str(value), "%Y-%m-%d %H:%M:%S")
    except Exception:
        try:
            parsed = parser.parse(str(value))
        except Exception:
            return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(datetime.timezone.utc).replace(tzinfo=None)
    return parsed


def _caption_refresh_hours(template: dict) -> float:
    """Return the maximum age for a stored caption before refreshing it."""

    try:
        frequency = int(float(template.get("frequency", 30)))
    except Exception:
        frequency = 30

    hours = 24.0
    if frequency <= 30:
        hours = 8.0
    if frequency <= 5:
        hours = 3.0

    if _truthy_template_value(template.get("livecaption")):
        hours = max(1.0, frequency / 7)

    return hours


def _caption_refresh_due(template: dict, now: datetime.datetime | None = None) -> bool:
    """Return True when the camera needs a fresh LLM caption."""

    if (template.get("last_caption", "") or "") == "":
        return True
    last_caption_time = _template_timestamp(template.get("last_caption_time"))
    if last_caption_time is None:
        return True
    now = now or datetime.datetime.utcnow()
    return now - last_caption_time > datetime.timedelta(
        hours=_caption_refresh_hours(template)
    )


def _scene_changed(
    previous_signature: str | None, current_signature: str | None, threshold: int
) -> tuple[bool, int | None]:
    """Return whether scene changed plus computed distance."""

    if not current_signature:
        return True, None
    if not previous_signature:
        return True, None
    distance = _scene_hamming_distance(previous_signature, current_signature)
    if distance is None:
        return True, None
    return distance >= max(1, threshold), distance


class CLIPProcessor:
    """Lightweight CLIP preprocessor used with ONNX models.

    This avoids the heavy ``transformers`` dependency by providing the
    minimal functionality needed for object filtering.
    """

    def __init__(self):
        pass

    @classmethod
    def from_pretrained(cls, _name: str) -> "CLIPProcessor":
        """Return a basic processor instance."""

        return cls()

    def __call__(self, text, images, return_tensors="np", padding=True):
        token_ids = [ord(c) for c in (text[0] if text else "")][:77]
        input_ids = np.zeros((1, 77), dtype=np.int64)
        attention_mask = np.zeros((1, 77), dtype=np.int64)
        input_ids[0, : len(token_ids)] = token_ids
        attention_mask[0, : len(token_ids)] = 1

        img = images.convert("RGB").resize((224, 224))
        img_array = (np.array(img).astype("float32") / 255.0).transpose(2, 0, 1)
        pixel_values = np.expand_dims(img_array, 0)

        return {
            "input_ids": input_ids,
            "attention_mask": attention_mask,
            "pixel_values": pixel_values,
        }


logging.getLogger("apscheduler").setLevel(logging.WARNING)

_clip_state = {"processor": None, "session": None}

# Track currently running jobs to avoid launching duplicates.
active_jobs: dict[str, multiprocessing.Process] = {}
# Use an RLock to prevent deadlocks when register_job_failure is invoked
# while the lock is already held in run_with_timeout.
active_jobs_lock = threading.RLock()
# Track failures and backoff time to slow down flapping jobs.
job_failures: dict[str, int] = {}
job_backoff_until: dict[str, float] = {}
# Long cooldown for persistently failing jobs.
job_circuit_open_until: dict[str, float] = {}
job_circuit_next_probe: dict[str, float] = {}
_circuit_log_last: dict[str, float] = {}
_shutdown_event = threading.Event()
_shutdown_grace_seconds = int(os.getenv("SCHEDULER_SHUTDOWN_GRACE_SECONDS", "5"))
_capture_fail_last_log: dict[str, float] = {}
_offline_jobs_run_lock = threading.Lock()

# Lightweight scheduler saturation telemetry (in-memory, resets on restart).
_scheduler_health_lock = threading.Lock()
_scheduler_max_instance_skips_total = 0
_scheduler_last_max_instance_at: str | None = None
_scheduler_job_max_instance_skips: dict[str, int] = {}


def mark_shutdown() -> None:
    """Signal that shutdown has begun to block new job launches."""
    _shutdown_event.set()


class GracefulAPScheduler(APScheduler):
    def __init__(self):
        super().__init__()
        self._scheduler = None
        self.set_scheduler(BackgroundScheduler())
        self._running_jobs = 0
        self._running_jobs_lock = threading.Lock()
        self._all_jobs_done = threading.Event()
        self._all_jobs_done.set()
        self._shutdown_called = False

    def set_scheduler(self, scheduler):
        self._scheduler = scheduler
        self._shutdown_called = False
        _shutdown_event.clear()
        self._scheduler.add_listener(
            self._track_job_state,
            EVENT_JOB_SUBMITTED
            | EVENT_JOB_EXECUTED
            | EVENT_JOB_ERROR
            | EVENT_JOB_MAX_INSTANCES,
        )

    def _track_job_state(self, event) -> None:
        global _scheduler_last_max_instance_at, _scheduler_max_instance_skips_total

        if event.code == EVENT_JOB_MAX_INSTANCES:
            job_id = getattr(event, "job_id", "unknown")
            with _scheduler_health_lock:
                _scheduler_max_instance_skips_total += 1
                _scheduler_last_max_instance_at = datetime.datetime.now().isoformat()
                _scheduler_job_max_instance_skips[job_id] = (
                    _scheduler_job_max_instance_skips.get(job_id, 0) + 1
                )
            return

        if event.code == EVENT_JOB_SUBMITTED:
            with self._running_jobs_lock:
                self._running_jobs += 1
                self._all_jobs_done.clear()
            return
        with self._running_jobs_lock:
            if self._running_jobs > 0:
                self._running_jobs -= 1
            if self._running_jobs == 0:
                self._all_jobs_done.set()

    def shutdown(self, wait=True):
        try:
            if self._shutdown_called:
                return
            self._shutdown_called = True
            if self.running:
                _shutdown_event.set()
                try:
                    self._scheduler.pause()
                except Exception:
                    pass
                # Stop all running jobs
                for job in self._scheduler.get_jobs():
                    job.remove()
                if wait and self._running_jobs:
                    self._all_jobs_done.wait(timeout=_shutdown_grace_seconds)

                # Shutdown the scheduler
                scheduler_thread = getattr(self._scheduler, "_thread", None)
                if (
                    scheduler_thread is not None
                    and scheduler_thread is threading.current_thread()
                ):
                    wait = False
                try:
                    super().shutdown(wait)
                except RuntimeError as exc:
                    if "cannot join current thread" not in str(exc):
                        raise

                # Reinitialize scheduler for future use without requiring a
                # full application restart. This allows tests or other
                # components to continue scheduling jobs after shutdown.
                self.set_scheduler(BackgroundScheduler())
            else:
                logging.info("Scheduler is not running.")
        except Exception as e:
            logging.error(f"Error during scheduler shutdown: {e}")
        finally:
            logging.info("Scheduler shutdown complete.")


scheduler = GracefulAPScheduler()


def get_scheduler_health(top_n: int = 10) -> dict:
    """Return lightweight scheduler saturation telemetry."""

    with _scheduler_health_lock:
        top_jobs = sorted(
            _scheduler_job_max_instance_skips.items(),
            key=lambda item: item[1],
            reverse=True,
        )[: max(1, int(top_n))]
        total = _scheduler_max_instance_skips_total
        last_at = _scheduler_last_max_instance_at

    with scheduler._running_jobs_lock:  # noqa: SLF001 - internal telemetry only
        running_jobs = scheduler._running_jobs  # noqa: SLF001 - internal telemetry only

    return {
        "browser_queue": browser_queue.health(),
        "max_instance_skips_total": total,
        "last_max_instance_at": last_at,
        "running_jobs": running_jobs,
        "top_skipped_jobs": [
            {"job_id": job_id, "count": count} for job_id, count in top_jobs
        ],
    }


def _rate_limited_job_log(level: str, key: str, message: str) -> None:
    """Log at most once per LOG_RATE_LIMIT_SEC per key."""

    now = time.time()
    if now - _circuit_log_last.get(key, 0) < LOG_RATE_LIMIT_SEC:
        return
    _circuit_log_last[key] = now
    getattr(logging, level, logging.info)(message)


def _circuit_remaining_seconds(key: str) -> float:
    """Return remaining open-circuit cooldown for *key* in seconds."""

    return max(0.0, job_circuit_open_until.get(key, 0.0) - time.time())


def register_job_failure(key: str) -> None:
    """Increment failure count, backoff, and optional open-circuit cooldown."""

    with active_jobs_lock:
        fails = job_failures.get(key, 0) + 1
        job_failures[key] = fails
        job_backoff_until[key] = time.time() + min(2**fails, 300)
        if fails >= JOB_CIRCUIT_FAILURE_THRESHOLD:
            now = time.time()
            until = now + JOB_CIRCUIT_COOLDOWN_SECONDS
            prior_until = job_circuit_open_until.get(key, 0.0)
            job_circuit_open_until[key] = max(prior_until, until)
            # Half-open probe cadence so recovery is detected without hammering.
            job_circuit_next_probe[key] = max(
                job_circuit_next_probe.get(key, 0.0), now + JOB_CIRCUIT_PROBE_SECONDS
            )
            try:
                mark_offline(key)
            except Exception:
                pass
            _rate_limited_job_log(
                "warning",
                f"circuit-open:{key}",
                (
                    f"Circuit opened for {key}: {fails} consecutive failures "
                    f"(cooldown {JOB_CIRCUIT_COOLDOWN_SECONDS}s, "
                    f"probe every {JOB_CIRCUIT_PROBE_SECONDS}s)"
                ),
            )


_WORKER_CAPTURE_FAILED = 2
_WORKER_CAPTURE_DEFERRED = 3


def _run_target(func, args):
    """Run a bounded worker without finalizing inherited scheduler threads."""
    if setproctitle:
        title = getattr(func, "__name__", "job")
        if args and isinstance(args[0], str):
            title += f":{args[0]}"
        setproctitle(f"glimpser {title}")
    exit_code = 1
    try:
        key = (
            args[0]
            if args and isinstance(args[0], str)
            else getattr(func, "__name__", "job")
        )
        failures_before = job_failures.get(key, 0)
        result = func(*args)
        # Failure counters live in process memory. A child can record a failed
        # capture and return normally; the parent must not mistake that for a
        # successful frame and erase its own backoff history.
        if job_failures.get(key, 0) > failures_before:
            exit_code = _WORKER_CAPTURE_FAILED
        elif isinstance(result, str) and result in {
            CAPTURE_STALE_BROWSER_SLOT_BUSY,
            CAPTURE_STALE_PREVIOUS,
        }:
            exit_code = _WORKER_CAPTURE_DEFERRED
        else:
            exit_code = 0
    except SystemExit as exc:
        exit_code = exc.code if isinstance(exc.code, int) else int(exc.code is not None)
        if exit_code == _WORKER_CAPTURE_DEFERRED:
            exit_code = 1  # An explicit SystemExit is not our capture deferral.
    except Exception:
        logging.exception("Unhandled exception in %s", getattr(func, "__name__", "job"))
        exit_code = 1
    finally:
        if multiprocessing.parent_process() is not None:
            # A fork from ThreadPoolExecutor inherits its thread-exit registry.
            # Python's normal child shutdown then tries to join the very thread
            # executing this worker and exits 1 even after a successful capture.
            # The job has already unwound its own context managers/finally blocks;
            # flush its output and exit without running parent thread finalizers.
            for stream in (sys.stdout, sys.stderr):
                try:
                    stream.flush()
                except Exception:
                    pass
            os._exit(exit_code)
    if exit_code:
        sys.exit(exit_code)


def _defer_camera_for_resources(func, args, timeout):
    """Keep one short retry per camera without declaring its source offline."""
    if func is not update_camera or not args or not scheduler.running:
        return
    name = args[0]
    current = get_template(name)
    if not current or _template_is_archived(current):
        return
    job_id = f"resource_retry:{name}"
    # Preserve an existing ticket's place instead of pushing it back each turn.
    if scheduler.get_job(job_id):
        return
    try:
        scheduler.add_job(
            id=job_id,
            func=schedule_camera_capture,
            trigger="date",
            run_date=datetime.datetime.now(datetime.timezone.utc)
            + datetime.timedelta(seconds=30 + random.randrange(30)),
            args=[name, {}, timeout],
            executor=camera_executor(current),
            max_instances=1,
            misfire_grace_time=300,
            coalesce=True,
            replace_existing=False,
        )
    except Exception:
        logging.exception("Could not defer capture for %s", name)


def _terminate_timed_out_worker(process) -> None:
    """Stop a worker and descendants observed before it can orphan them."""
    descendants = []
    pid = getattr(process, "pid", None)
    if isinstance(pid, int) and pid > 0:
        try:
            descendants = psutil.Process(pid).children(recursive=True)
        except psutil.NoSuchProcess:
            pass
        except psutil.Error as exc:
            logging.warning("Cannot inspect timed-out worker descendants: %s", exc)

    process.terminate()
    # Keep psutil Process identities captured while ownership was provable.
    # Their signal methods guard against PID reuse; never match by process name.
    for child in reversed(descendants):
        try:
            child.terminate()
        except psutil.NoSuchProcess:
            pass
        except psutil.Error as exc:
            logging.warning("Cannot terminate worker descendant: %s", exc)
    process.join(5)
    if process.is_alive():
        if hasattr(process, "kill"):
            process.kill()
            process.join(5)
        logging.warning("Process kill required after timeout")
    if descendants:
        _, alive = psutil.wait_procs(descendants, timeout=1)
        for child in alive:
            try:
                child.kill()
            except psutil.NoSuchProcess:
                pass
            except psutil.Error as exc:
                logging.warning("Cannot kill worker descendant: %s", exc)
        psutil.wait_procs(alive, timeout=1)


def run_with_timeout(func, args=(), timeout=300):
    """Run *func* in a separate process with a timeout.

    If the system appears offline or process creation fails, the job is skipped
    and the associated template is marked offline when possible.
    """
    if _shutdown_event.is_set():
        logging.info(
            "Shutdown in progress; skipping job %s",
            getattr(func, "__name__", "unknown"),
        )
        return

    if not is_system_online():
        state = network_state()
        logging.warning(
            "System offline (lan_ok=%s wan_ok=%s dns_ok=%s), skipping job %s",
            state.get("lan_ok"),
            state.get("wan_ok"),
            state.get("dns_ok"),
            getattr(func, "__name__", "unknown"),
        )
        if args and isinstance(args[0], str):
            try:
                mark_offline(args[0])
            except Exception:
                pass
        session = SessionLocal()
        try:
            session.add(
                OfflineJob(
                    function=f"{func.__module__}.{func.__name__}",
                    args=json.dumps(list(args)),
                    timeout=timeout,
                    timestamp=int(time.time()),
                )
            )
            session.commit()
        except Exception as exc:
            session.rollback()
            logging.error("Failed to queue offline job: %s", exc)
        finally:
            session.close()
        return

    # Nonblocking psutil samples average since this thread's previous call.
    # A browser worker may have spent that entire interval rendering, causing
    # the next (oldest) ticket to inherit its load and repeatedly lose admission.
    # A short fixed window measures current pressure, independent of job length.
    cpu_level = psutil.cpu_percent(interval=0.1)
    if cpu_level > WATCHDOG_CPU_THRESHOLD:
        logging.info(
            "High CPU (%.1f%%); deferring job %s",
            cpu_level,
            getattr(func, "__name__", "job"),
        )
        _defer_camera_for_resources(func, args, timeout)
        return

    mem_level = psutil.virtual_memory().percent
    if mem_level > WATCHDOG_MEMORY_THRESHOLD:
        logging.info(
            "High memory (%.1f%%); deferring job %s",
            mem_level,
            getattr(func, "__name__", "job"),
        )
        _defer_camera_for_resources(func, args, timeout)
        return

    # Determine key for tracking active jobs. For camera updates the first
    # argument is the camera name; otherwise fall back to function name.
    key = getattr(func, "__name__", "job")
    if args and isinstance(args[0], str):
        key = args[0]

    try:
        with active_jobs_lock:
            now = time.time()
            circuit_remaining = _circuit_remaining_seconds(key)
            if circuit_remaining > 0:
                now = time.time()
                next_probe = job_circuit_next_probe.get(
                    key, now + JOB_CIRCUIT_PROBE_SECONDS
                )
                if now < next_probe:
                    _rate_limited_job_log(
                        "info",
                        f"circuit-skip:{key}",
                        (
                            f"Circuit open for {key}; skipping for {circuit_remaining:.0f}s "
                            f"(next probe in {max(0, int(next_probe - now))}s)"
                        ),
                    )
                    return
                job_circuit_next_probe[key] = now + JOB_CIRCUIT_PROBE_SECONDS
                _rate_limited_job_log(
                    "info",
                    f"circuit-probe:{key}",
                    (
                        f"Circuit half-open probe for {key} "
                        f"({circuit_remaining:.0f}s cooldown remaining)"
                    ),
                )
            backoff_until = job_backoff_until.get(key, 0)
            if now < backoff_until:
                logging.info("backing off job %s for %.1fs", key, backoff_until - now)
                return
            existing = active_jobs.get(key)
            if existing and existing.is_alive():
                logging.info("job already running")
                return
            proc_title = getattr(func, "__name__", "job")
            if args and isinstance(args[0], str):
                proc_title += f":{args[0]}"
            process = multiprocessing.Process(
                target=_run_target,
                args=(func, args),
                name=f"glimpser {proc_title}",
            )
            active_jobs[key] = process
        process.start()
    except OSError as exc:
        logging.error(
            "Failed to start process for %s: %s",
            getattr(func, "__name__", "unknown"),
            exc,
        )
        if args and isinstance(args[0], str):
            try:
                mark_offline(args[0])
            except Exception:
                pass
        with active_jobs_lock:
            active_jobs.pop(key, None)
        return False

    process.join(timeout)
    success = True
    deferred = False
    if process.is_alive():
        _terminate_timed_out_worker(process)
        logging.warning("Process terminated due to timeout")
        success = False
        if args and isinstance(args[0], str):
            try:
                mark_offline(args[0])
            except Exception:
                pass
            try:
                if len(args) > 1 and isinstance(args[1], dict):
                    url = args[1].get("url")
                    if url:
                        cas_error(url)
            except Exception:
                pass
    elif process.exitcode == _WORKER_CAPTURE_DEFERRED:
        deferred = True
    elif process.exitcode and process.exitcode != 0:
        success = False

    with active_jobs_lock:
        active_jobs.pop(key, None)
        if success and not deferred:
            job_failures.pop(key, None)
            job_backoff_until.pop(key, None)
            job_circuit_open_until.pop(key, None)
            job_circuit_next_probe.pop(key, None)

    if not success:
        register_job_failure(key)
    return None if deferred else success


def safe_symlink(src: str, dst: str) -> None:
    """Create ``dst`` pointing to ``src`` replacing any existing link.

    Both paths must reside under ``SCREENSHOT_DIRECTORY`` to avoid
    creating links outside the managed tree.
    """

    src_path = os.path.abspath(src)
    dst_path = os.path.abspath(dst)

    base = os.path.abspath(SCREENSHOT_DIRECTORY)
    # Reject paths outside the screenshot directory to mitigate
    # symlink attacks on arbitrary locations.
    resolved_base = os.path.realpath(base)
    # Compare path components and resolve parent links; a sibling named
    # "screenshots-other" or a linked subdirectory is not inside our storage.
    if (
        os.path.commonpath([base, src_path]) != base
        or os.path.commonpath([base, dst_path]) != base
        or os.path.commonpath([resolved_base, os.path.realpath(src_path)])
        != resolved_base
        or os.path.commonpath(
            [resolved_base, os.path.realpath(os.path.dirname(dst_path))]
        )
        != resolved_base
    ):
        raise ValueError("symlink paths must stay within screenshot directory")
    if not os.path.exists(src_path):
        raise FileNotFoundError(src_path)

    if os.path.lexists(dst_path):
        try:
            os.remove(dst_path)
        except FileNotFoundError:
            # The link vanished after the existence check
            pass
    os.makedirs(os.path.dirname(dst_path), exist_ok=True)
    try:
        os.symlink(src_path, dst_path)
    except FileExistsError:
        # Another process recreated the link after we removed it.
        try:
            os.remove(dst_path)
        except FileNotFoundError:
            pass
        os.symlink(src_path, dst_path)


def _existing_managed_sidecar_target(path: str, directory: str) -> str | None:
    """Return a sidecar target only when it still points at a valid frame.

    ``os.path.exists`` returns ``False`` for dangling symlinks, while
    ``os.path.lexists`` returns ``True``. Motion sidecars are rotated with
    ``lexists`` so broken links can otherwise be preserved indefinitely and
    later trip artifact scans. Drop those stale links before creating the next
    motion sidecar.
    """

    if os.path.islink(path):
        destination = os.readlink(path)
        if not os.path.isabs(destination):
            destination = os.path.abspath(os.path.join(directory, destination))
        else:
            destination = os.path.abspath(destination)

        base = os.path.abspath(SCREENSHOT_DIRECTORY)
        if (
            os.path.commonpath([base, destination]) != base
            or os.path.commonpath(
                [os.path.realpath(base), os.path.realpath(destination)]
            )
            != os.path.realpath(base)
            or not os.path.exists(destination)
        ):
            try:
                os.remove(path)
            except FileNotFoundError:
                pass
            except OSError as exc:
                logging.debug("Unable to remove stale sidecar %s: %s", path, exc)
            return None
        return destination

    if os.path.isfile(path):
        return path

    if os.path.lexists(path):
        try:
            os.remove(path)
        except OSError as exc:
            logging.debug("Unable to remove invalid sidecar %s: %s", path, exc)
    return None


def _validate_latest_screenshot(path: str, name: str, url: str | None) -> bool:
    """Verify the latest screenshot looks readable before updating symlinks."""
    try:
        size = os.path.getsize(path)
        if size <= 0:
            raise ValueError("file size is zero")
        with Image.open(path) as img:
            img.verify()
        return True
    except (FileNotFoundError, UnidentifiedImageError, OSError, ValueError) as exc:
        status = get_cached_status_code(url) if url else None
        try:
            age_seconds = time.time() - os.path.getmtime(path)
        except OSError:
            age_seconds = None
        logging.warning(
            "Discarding invalid screenshot %s for %s (size=%s, age=%s, status=%s): %s",
            path,
            name,
            os.path.getsize(path) if os.path.exists(path) else "missing",
            f"{age_seconds:.1f}s" if age_seconds is not None else "unknown",
            status if status is not None else "unknown",
            exc,
        )
        try:
            os.remove(path)
        except OSError:
            pass
        return False


def _latest_source_template_screenshot(name: str, source_template: str) -> str | None:
    """Return the newest screenshot from ``source_template`` for a derived view."""

    if source_template == name:
        logging.warning("[%s] source_template cannot reference itself", name)
        return None

    screenshots = get_screenshots_for_template(source_template)
    if not screenshots:
        logging.warning(
            "[%s] source_template %s has no screenshots yet",
            name,
            source_template,
        )
        return None

    latest = os.path.join(SCREENSHOT_DIRECTORY, source_template, screenshots[0])
    if not os.path.isfile(latest):
        logging.warning(
            "[%s] source_template %s latest screenshot missing: %s",
            name,
            source_template,
            latest,
        )
        return None
    return latest


def _save_provided_screenshot(name: str, template: dict, image_file: str) -> bool:
    """Persist a supplied still through the normal capture postprocess path."""

    if not image_file or not os.path.isfile(image_file):
        logging.warning("[%s] provided screenshot missing: %s", name, image_file)
        return False

    timestamp = datetime.datetime.utcnow().strftime("%Y%m%d%H%M%S")
    final_path = os.path.join(SCREENSHOT_DIRECTORY, name, f"{name}_{timestamp}.png")
    os.makedirs(os.path.dirname(final_path), exist_ok=True)
    tmp_path = final_path + ".tmp"

    try:
        with Image.open(image_file) as image:
            # Keep uploads and source-template renders on the same enhancement
            # path as native captures so stabilization, burst fusion, and
            # composite rendering stay consistent across all still inputs.
            image = _postprocess_still_image(
                image,
                final_path,
                name,
                dark=bool(template.get("dark", False)),
                stabilize_mode=template.get("stabilize_mode", "off"),
            )
            image.save(tmp_path, "PNG")
        if os.path.exists(tmp_path) and _is_valid_png(tmp_path):
            add_timestamp(tmp_path, name, invert=template.get("invert", False))
            os.replace(tmp_path, final_path)
            parent = str(template.get("source_template") or "")
            if str(template.get("url", "")).startswith("ptzview:"):
                from app.utils.source_freshness import record_source

                record_source(
                    name,
                    template["url"],
                    inherited=datetime.datetime.fromtimestamp(
                        os.path.getmtime(image_file), datetime.timezone.utc
                    ).isoformat(),
                    capture_file=os.path.basename(final_path),
                )
            if parent and parent != "hubitat_site_dashboard":
                from app.utils.source_freshness import record_derived_source

                record_derived_source(name, parent, image_file, final_path)
            return True
    except Exception as exc:
        logging.warning("[%s] provided screenshot save failed: %s", name, exc)
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
    return False


def update_camera(name, template, image_file=None, motion=False):
    # just ignore the old
    template = get_template(name)

    # These dashboards arrive from Housebot's site capture timer. Polling the
    # cloud URL would replace successful local captures with cloud failures.
    if (
        template.get("source_template") == "hubitat_site_dashboard"
        and image_file is None
    ):
        return None

    lsuc = False
    source_template = validate_template_name(
        str(template.get("source_template") or "").strip()
    )
    source_template_profile_flags = {
        "ais_map",
        "hubitat_cloud_dashboard",
        "hubitat_site_dashboard",
        "map_dashboard",
    }
    if (
        image_file is None
        and source_template
        and source_template not in source_template_profile_flags
    ):
        image_file = _latest_source_template_screenshot(name, source_template)

    if image_file is None:
        from app.utils import ptz_views

        lsuc = ptz_views.capture(
            name,
            template,
            lambda: capture_or_download(name, template),
            lambda path: _save_provided_screenshot(name, template, path),
        )
    else:
        lsuc = _save_provided_screenshot(name, template, image_file)

    url = template.get("url")

    if is_stale_capture_result(lsuc):
        set_capture_stale(name, str(lsuc))
        if lsuc == CAPTURE_STALE_BROWSER_SLOT_BUSY:
            browser_queue.enqueue(name, template)
        return lsuc

    if lsuc is not True:
        entry = throttle_cache.get(url)
        if entry and entry.get("reason") in {"lan_offline", "local_unreachable"}:
            now = time.time()
            window = LAN_OFFLINE_DISABLE_WINDOW_MINUTES * 60
            first = entry.get("first")
            if not first or now - first > window:
                entry["first"] = now
                entry["errors"] = 1
            else:
                entry["errors"] = entry.get("errors", 0) + 1
            if entry["errors"] >= 2:
                entry["timeout"] = max(
                    entry.get("timeout", 0),
                    now + LAN_OFFLINE_BACKOFF_SECONDS,
                )
            if entry["errors"] >= LAN_OFFLINE_DISABLE_ERRORS and not entry.get(
                "lan_offline_marked"
            ):
                mark_offline(name)
                entry["lan_offline_marked"] = True
                clean_url = sanitize_url(url)
                logging.warning(
                    "Auto-marking %s offline after %d LAN failures in %d minutes (%s)",
                    name,
                    entry["errors"],
                    LAN_OFFLINE_DISABLE_WINDOW_MINUTES,
                    clean_url,
                )
        if (
            entry
            and entry.get("errors", 0) >= 10
            and time.time() - entry.get("first", time.time()) > 60 * 60 * 24
        ):
            mark_offline(name)
        clean_url = sanitize_url(url)
        now = time.monotonic()
        last_log = _capture_fail_last_log.get(name, 0.0)
        reason = entry.get("reason") if entry else None
        set_capture_failed(name, True, reason or "")
        backoff_active = bool(entry and entry.get("timeout", 0) > time.time())
        rate_limit = LOG_RATE_LIMIT_SEC
        if reason == "lan_offline":
            rate_limit = max(rate_limit, 300)
        if backoff_active:
            # Avoid repeating noisy "Capture failed" logs for sources that are
            # already in an explicit backoff/quarantine window.
            rate_limit = max(rate_limit, 300)
        if now - last_log >= rate_limit:
            _capture_fail_last_log[name] = now
            prefix = "[LAN_OFFLINE] " if reason == "lan_offline" else ""
            if backoff_active:
                logging.debug(
                    "%sCapture paused for %s (%s) due to %s backoff",
                    prefix,
                    name,
                    clean_url,
                    reason or "active",
                )
            elif entry and entry.get("errors", 0) > 2:
                logging.debug("%sCapture failed for %s (%s)", prefix, name, clean_url)
            else:
                logging.error("%sCapture failed for %s (%s)", prefix, name, clean_url)
        register_job_failure(name)
        return None

    if lsuc is True:
        directory = os.path.join(SCREENSHOT_DIRECTORY, name)
        png_files = [
            f
            for f in os.listdir(directory)
            if f.endswith(".png")
            and os.path.isfile(os.path.join(directory, f))
            and not os.path.islink(os.path.join(directory, f))
        ]
        if not png_files:
            return None  # camera is out

        png_files = sort_canonical_screenshot_filenames(name, png_files)
        if not png_files:
            return None

        # link for other processes to use
        lpath = os.path.join(SCREENSHOT_DIRECTORY, "latest_camera.png")
        latest_image_path = os.path.join(directory, png_files[-1])
        if not _validate_latest_screenshot(latest_image_path, name, url):
            set_capture_stale(name, "invalid_latest_frame")
            return None

        captured_at = parse_canonical_screenshot_timestamp(name, png_files[-1])
        # Validation must precede metadata publication. A retried check may have
        # produced no new file, and processing may finish long after acquisition.
        update_last_screenshot_time(name, captured_at=captured_at)
        set_capture_failed(name, False)

        clean_path = os.path.join(directory, "last_clean.png")
        # A clean companion belongs to one immutable capture filename. This
        # prevents an old image request from receiving a newer clean copy.
        companion = latest_image_path + ".clean.png"
        try:
            if not os.path.exists(companion):
                shutil.copy2(latest_image_path, companion + ".tmp")
                os.replace(companion + ".tmp", companion)
            if os.path.lexists(clean_path + ".tmp"):
                os.unlink(clean_path + ".tmp")
            os.symlink(os.path.abspath(companion), clean_path + ".tmp")
            os.replace(clean_path + ".tmp", clean_path)
            companions = sorted(
                Path(directory).glob("*.png.clean.png"), key=lambda p: p.name
            )
            for obsolete in companions[:-2]:
                obsolete.unlink(missing_ok=True)
        except OSError as exc:
            logging.debug("Unable to update clean screenshot for %s: %s", name, exc)

        try:
            if os.path.lexists(lpath + ".tmp"):
                os.unlink(os.path.abspath(lpath + ".tmp"))
            safe_symlink(
                os.path.abspath(
                    os.path.join(SCREENSHOT_DIRECTORY, name, png_files[-1])
                ),
                os.path.abspath(lpath + ".tmp"),
            )
            os.rename(os.path.abspath(lpath + ".tmp"), os.path.abspath(lpath))

            lpath = os.path.join(SCREENSHOT_DIRECTORY, name, "latest_camera.png")
            if os.path.lexists(lpath + ".tmp"):
                os.unlink(os.path.abspath(lpath + ".tmp"))
            safe_symlink(
                os.path.abspath(
                    os.path.join(SCREENSHOT_DIRECTORY, name, png_files[-1])
                ),
                os.path.abspath(lpath + ".tmp"),
            )
            os.rename(os.path.abspath(lpath + ".tmp"), os.path.abspath(lpath))

            # Create symlinks for each valid group
            if "groups" in template:
                groups = [g.strip() for g in template["groups"].split(",") if g.strip()]
                for group in groups:
                    valid_group = validate_group_name(group)
                    if not valid_group:
                        logging.warning("Ignoring invalid group name: %s", group)
                        continue
                    group_lpath = os.path.join(
                        SCREENSHOT_DIRECTORY, f"{valid_group}_latest_camera.png"
                    )
                    if os.path.lexists(group_lpath + ".tmp"):
                        os.unlink(os.path.abspath(group_lpath + ".tmp"))
                    safe_symlink(
                        os.path.abspath(
                            os.path.join(SCREENSHOT_DIRECTORY, name, png_files[-1])
                        ),
                        os.path.abspath(group_lpath + ".tmp"),
                    )
                    os.rename(
                        os.path.abspath(group_lpath + ".tmp"),
                        os.path.abspath(group_lpath),
                    )

        except Exception:
            pass

        caption_refresh_due = _caption_refresh_due(template)
        motion_config = template.get("motion", 1)
        if (
            not motion
            and motion_config in [1, None]
            and (template.get("last_caption", "") or "") != ""
            and not caption_refresh_due
        ):
            return

        lsum = motion
        percentage_difference = 0

        try:
            with Image.open(latest_image_path) as img:
                if is_mostly_blank(img):
                    status = get_cached_status_code(url)
                    logging.info(
                        "Skipping blank frame for motion detection: %s (HTTP status: %s)",
                        latest_image_path,
                        status if status is not None else "unknown",
                    )
                    return
        except Exception as e:
            logging.warning("Error checking blank frame %s: %s", latest_image_path, e)
            return

        if len(png_files) > 1:
            percentage_difference = calculate_difference_fast(
                os.path.join(directory, png_files[-2]),
                latest_image_path,
            )
            if (percentage_difference or 0) >= float(template.get("motion", 0)):
                lsum = True
        elif len(png_files) == 1:
            lsum = True

        scene_signature = _compute_scene_signature(latest_image_path)
        previous_scene_signature = (template.get("last_scene_signature") or "").strip()
        scene_threshold = _scene_change_threshold(template)
        scene_changed, scene_distance = _scene_changed(
            previous_scene_signature, scene_signature, scene_threshold
        )
        if scene_signature:
            template["last_scene_signature"] = scene_signature
        if scene_distance is not None:
            template["last_scene_hamming"] = str(scene_distance)
        if scene_changed:
            template["last_scene_change_time"] = datetime.datetime.utcnow().strftime(
                "%Y-%m-%d %H:%M:%S"
            )

        prev_motion = os.path.join(directory, "last_motion.png")

        allow = motion

        #  Work through, Motion detection, then object detection, then live caption, then online captioning
        #
        last_caption_time, _last_motion_caption = None, None
        last_caption_trigger, last_motion_trigger = motion, motion

        if caption_refresh_due:
            allow = True
            last_caption_trigger = True
        if (template.get("last_motion_caption", "") or "") == "":
            allow = True
            last_motion_trigger = True

        if lsum is True:
            allow = True
            last_motion_trigger = True
            # Event-buffer cameras need current captions for activity alerts.
            if str(template.get("event_buffer_enabled", "")).lower() in {"1", "true"}:
                last_caption_trigger = True

        if allow is False:
            try:
                last_motion_caption_time = datetime.datetime.strptime(
                    template.get("last_motion_caption_time", "1970-01-01 00:00:00"),
                    "%Y-%m-%d %H:%M:%S",
                )
                if (
                    last_motion_caption_time
                    and datetime.datetime.utcnow() - last_motion_caption_time
                    > datetime.timedelta(hours=3)
                ):
                    allow = True
                    last_motion_trigger = True
            except Exception:
                pass

        scene_change_gate = template.get("scene_change_gate", "true") or "true"
        scene_change_gate = _truthy_template_value(scene_change_gate)
        live_caption_enabled = _truthy_template_value(template.get("livecaption"))
        if (
            scene_change_gate
            and not live_caption_enabled
            and not scene_changed
            and last_caption_trigger
            and (template.get("last_caption", "") or "") != ""
            and not motion
            and not caption_refresh_due
        ):
            # No meaningful frame change since last scene signature; keep previous caption.
            last_caption_trigger = False

        # Implement a filter using CLIP
        object_filter = template.get("object_filter", "")
        object_confidence = 0.5
        try:
            object_confidence = float(template.get("object_confidence", 0.5))
        except Exception:
            pass

        # run the object detect AFTER the motion detetor
        if allow is True and object_filter and object_confidence is not None:
            clip_state = _clip_state

            # Prefer the lightweight ONNX backend when available
            use_onnx = ort is not None

            if use_onnx:
                if clip_state["session"] is None:
                    # Prefer GPU when available and fall back to CPU. This uses
                    # the providers reported by onnxruntime so it works even
                    # when CUDA is not installed.
                    available = getattr(ort, "get_available_providers", lambda: [])()
                    providers = (
                        ["CUDAExecutionProvider"]
                        if "CUDAExecutionProvider" in available
                        else ["CPUExecutionProvider"]
                    )
                    try:
                        clip_state["session"] = ort.InferenceSession(
                            CLIP_MODEL_PATH, providers=providers
                        )
                    except TypeError:
                        # Some runtimes (or tests) may not accept the providers
                        # keyword. Fall back to default initialization.
                        clip_state["session"] = ort.InferenceSession(CLIP_MODEL_PATH)

                if clip_state["processor"] is None:
                    clip_state["processor"] = CLIPProcessor.from_pretrained(
                        CLIP_MODEL_NAME
                    )

                # Load the latest image
                latest_image_path = os.path.join(directory, png_files[-1])
                image = Image.open(latest_image_path)

                inputs = clip_state["processor"](
                    text=[object_filter],
                    images=image,
                    return_tensors="np",
                    padding=True,
                )

                outputs = clip_state["session"].run(
                    None,
                    {
                        "input_ids": inputs["input_ids"],
                        "attention_mask": inputs["attention_mask"],
                        "pixel_values": inputs["pixel_values"],
                    },
                )
                logits = outputs[0]
                exp = np.exp(logits)
                probs = exp / exp.sum(axis=1, keepdims=True)
            else:
                # Skip detection when onnxruntime is unavailable
                probs = np.array([[0.0]])

            # Check if the object is detected with confidence higher than the threshold
            if probs[0, 0] >= object_confidence:
                allow = True

        if allow:
            # Allow this to run one time if we have no detection. If there is a
            # data/screenshots/<camera>/last_motion.png, rename the symlink to
            # prev_motion.png, then create the last_motion.png symlink to point
            # to the new png_files[-1].
            image_paths = []
            # add reference image if available
            if os.path.exists(os.path.join(directory, "reference.png")):
                image_paths.append(os.path.join(directory, "reference.png"))

            # Include previous motion frames when present so the captioner can
            # better detect changes between updates
            for extra in ["prev_motion.png", "last_motion.png"]:
                extra_path = os.path.join(directory, extra)
                if os.path.exists(extra_path):
                    image_paths.append(extra_path)

            # Find the image that closest matches the last_caption_time
            if "last_caption_time" in template and template["last_caption_time"] != "":
                try:
                    last_caption_time = parser.parse(template["last_caption_time"])
                    closest_image_filename = find_closest_image(
                        directory, last_caption_time
                    )
                    if closest_image_filename:
                        closest_image_path = os.path.join(
                            directory, closest_image_filename
                        )
                        logging.debug("last caption.... %s", closest_image_path)
                        image_paths.append(closest_image_path)
                except Exception as e:
                    logging.warning("caption parsing error %s", e)

            image_paths.append(os.path.join(directory, png_files[-1]))

            # Remove any duplicates while preserving order
            deduped = []
            for path in image_paths:
                if path not in deduped:
                    deduped.append(path)
            image_paths = deduped

            lctime = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

            # archictecture:
            #  check to see if there are any image in the object filter
            #  check to see if there are differences in the image
            #  check to see if there are alerts in the image -> no? use the
            #  llava caption
            #     yes?  use the gpt caption
            #

            #  add python llava (llama multimodal)  summarization. Compare the
            #  reference frame, the previous motion frame and the current frame
            #  together so captions reflect meaningful changes.

            lret = None
            # Reload settings before setting motion metadata; reloading afterwards
            # discarded the timestamp. Only actual image motion is an event:
            # periodic caption refreshes and empty captions are not activity.
            template = get_template(name)
            if lsum is True:
                template["last_motion_time"] = lctime
                # Publish promptly even if caption generation is slow or fails.
                if not save_caption_metadata(name, {"last_motion_time": lctime}):
                    logging.error("Motion metadata persistence failed for %s", name)

            lret = None

            if last_caption_trigger or template.get("last_caption") is None:
                lprompt = ""
                if template.get("notes"):
                    lprompt += template["notes"].strip() + "\n---\n"

                # Include changing device evidence in the scene-cache identity too.
                from app.utils.caption_context import caption_context

                lprompt += "\n[caption-evidence:v4]\n" + caption_context(
                    name, image_paths
                )
                cached_caption = _caption_cache_get(directory, scene_signature, lprompt)
                if cached_caption:
                    gret = cached_caption
                    logging.debug("Reused cached scene caption for %s", name)
                else:
                    #  use Chatgpt_compare with notes separated for clarity
                    gret = chatgpt_compare(lprompt, image_paths, template_name=name)
                    if usable_caption(gret):
                        _caption_cache_set(directory, scene_signature, lprompt, gret)

                if gret and not usable_caption(gret):
                    template["last_ret"] = gret + "*"
                    caption_overlay = template.get("last_caption")
                elif gret:
                    template["last_caption"] = gret
                    template["last_caption_time"] = lctime
                    caption_overlay = gret
                else:
                    template["last_ret"] = f"Caption refresh failed at {lctime}"
                    caption_overlay = template.get("last_caption")
                add_motion_and_caption(lpath, caption=caption_overlay, motion=lsum)
            elif lret is not None:
                add_motion_and_caption(lpath, caption=lret, motion=lsum)
            else:
                lcap = template.get(
                    "last_caption", template.get("last_motion_caption", None)
                )
                add_motion_and_caption(lpath, caption=lcap, motion=lsum)

            if not save_caption_metadata(name, template):
                logging.error("Caption metadata persistence failed for %s", name)
                return
            if template.get("callback_url"):
                payload = {
                    "name": name,
                    "caption": template.get("last_caption"),
                    "timestamp": lctime,
                    "motion": bool(lsum),
                }
                event = "caption" if last_caption_trigger else "motion"
                send_http_callback(template.get("callback_url"), event, payload)

            if last_motion_trigger or lsum:
                if os.path.lexists(
                    os.path.join(directory, "last_motion_caption.png.tmp")
                ):
                    os.remove(os.path.join(directory, "last_motion_caption.png.tmp"))
                safe_symlink(
                    os.path.join(directory, png_files[-1]),
                    os.path.join(directory, "last_motion_caption.png.tmp"),
                )
                os.rename(
                    os.path.join(directory, "last_motion_caption.png.tmp"),
                    os.path.join(directory, "last_motion_caption.png"),
                )

            if last_caption_trigger:
                if os.path.lexists(os.path.join(directory, "last_caption.png.tmp")):
                    os.remove(os.path.join(directory, "last_caption.png.tmp"))
                safe_symlink(
                    os.path.join(directory, png_files[-1]),
                    os.path.join(directory, "last_caption.png.tmp"),
                )
                os.rename(
                    os.path.join(directory, "last_caption.png.tmp"),
                    os.path.join(directory, "last_caption.png"),
                )

            if os.path.lexists(prev_motion):
                prev_motion_tmp = os.path.join(directory, "prev_motion.png.tmp")
                prev_motion_link = os.path.join(directory, "prev_motion.png")
                if os.path.lexists(prev_motion_tmp):
                    os.remove(prev_motion_tmp)
                if os.path.islink(prev_motion):
                    destination = _existing_managed_sidecar_target(
                        prev_motion, directory
                    )
                    if destination:
                        safe_symlink(destination, prev_motion_tmp)
                        os.rename(prev_motion_tmp, prev_motion_link)
                        image_paths.append(prev_motion_link)
                elif os.path.isfile(prev_motion):
                    os.replace(prev_motion, prev_motion_tmp)
                    os.rename(prev_motion_tmp, prev_motion_link)
                    image_paths.append(prev_motion_link)
                else:
                    _existing_managed_sidecar_target(prev_motion, directory)
            if os.path.lexists(os.path.join(directory, "last_motion.png.tmp")):
                os.remove(os.path.join(directory, "last_motion.png.tmp"))
            safe_symlink(
                os.path.join(directory, png_files[-1]),
                os.path.join(directory, "last_motion.png.tmp"),
            )
            os.rename(
                os.path.join(directory, "last_motion.png.tmp"),
                os.path.join(directory, "last_motion.png"),
            )

        elif lsum is True:
            # just ignore the old
            template = get_template(name)

            lcap = template.get(
                "last_caption", template.get("last_motion_caption", None)
            )
            add_motion_and_caption(lpath, caption=lcap, motion=lsum)
            lctime = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            template["last_motion_time"] = lctime
            if not save_caption_metadata(name, template):
                logging.error("Motion metadata persistence failed for %s", name)
                return
            if template.get("callback_url"):
                payload = {
                    "name": name,
                    "caption": template.get("last_caption"),
                    "timestamp": lctime,
                    "motion": True,
                }
                send_http_callback(template.get("callback_url"), "motion", payload)

            if os.path.lexists(prev_motion):
                if os.path.lexists(os.path.join(directory, "prev_motion.png.tmp")):
                    os.remove(os.path.join(directory, "prev_motion.png.tmp"))
                if os.path.islink(prev_motion):
                    destination = _existing_managed_sidecar_target(
                        prev_motion, directory
                    )
                    if destination:
                        safe_symlink(
                            destination,
                            os.path.join(directory, "prev_motion.png.tmp"),
                        )
                        os.rename(
                            os.path.join(directory, "prev_motion.png.tmp"),
                            os.path.join(directory, "prev_motion.png"),
                        )
                elif os.path.isfile(prev_motion):
                    os.replace(prev_motion, os.path.join(directory, "prev_motion.png"))
                else:
                    _existing_managed_sidecar_target(prev_motion, directory)
            if os.path.lexists(os.path.join(directory, "last_motion.png.tmp")):
                os.remove(os.path.join(directory, "last_motion.png.tmp"))
            safe_symlink(
                os.path.join(directory, png_files[-1]),
                os.path.join(directory, "last_motion.png.tmp"),
            )
            os.rename(
                os.path.join(directory, "last_motion.png.tmp"),
                os.path.join(directory, "last_motion.png"),
            )

        else:
            # just ignore the old
            template = get_template(name)

            lcap = template.get(
                "last_caption", template.get("last_motion_caption", None)
            )
            add_motion_and_caption(lpath, caption=lcap, motion=lsum)


def init_crawl():
    templates = list(
        get_templates().items()
    )  # Make sure to fetch the templates within this function

    random.shuffle(templates)
    for name, template in templates:
        if _template_is_archived(template):
            continue
        if _queued_browser_template(template):
            browser_queue.enqueue(name, template)
        else:
            update_camera(name, template)


def update_summary():  # noqa: PLR0912, PLR0915
    """Summarize recent camera activity and store structured results."""

    # summarize all of htis together
    lstring = (
        "The following are a list of real time dashboards and cameras, and their "
        "recent status updates:\n"
    )
    templates = get_templates_sorted_by_last_caption_time()

    for id, template in templates:
        name = template.get("name")
        if (
            _truthy_template_value(template.get("private_camera"))
            or "private" in str(template.get("groups") or "").casefold()
        ):
            continue
        if lstring.count("\n") > SUMMARY_MAX_LINES:
            break

        if template.get("last_caption_time"):
            caption_time = datetime.datetime.strptime(
                template.get("last_caption_time", ""), "%Y-%m-%d %H:%M:%S"
            )
            if (datetime.datetime.utcnow() - caption_time).total_seconds() > 3 * 3600:
                continue  # Skip templates older than 3 hours

            fnotes = SENTENCE_SPLIT_RE.split(str(template.get("notes") or "").strip())
            gnotes = SENTENCE_SPLIT_RE.split(
                str(template.get("last_caption") or "").strip()
            )

            if len(fnotes) > 0:
                try:
                    fnotes = [note for note in fnotes if note.strip()][0]
                except Exception:
                    pass

            if len(gnotes) > 0:
                try:
                    gnotes = " ".join([note for note in gnotes if note.strip()][0:-1])
                except Exception as e:
                    logging.error("error %s %s", e, template)
                    logging.debug("NOTES: %s", fnotes)
                    logging.debug("GNOTES: %s", gnotes)

            lstring += (
                "name: "
                + name
                + "\tgroups: "
                + template.get("groups", "")
                + "\tupdated: "
                + template.get("last_caption_time", "")
                + "\tprompt: "
                + str(fnotes)
                + "\tresponse: "
                + str(gnotes)
                + "\n"
            )

    output_path = os.path.join(SUMMARIES_DIRECTORY)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    history = None
    session = SessionLocal()
    try:
        try:
            summaries = session.query(Summary).order_by(Summary.timestamp.desc()).all()
        except OperationalError as exc:
            # If the DB path is misconfigured/unavailable at startup, avoid crashing
            # the scheduler thread; we'll try again on the next interval.
            logging.warning("Summary update skipped: database unavailable: %s", exc)
            return
        entries = []
        steps = [1, 3, 8, 24]
        for step in steps:
            if step < len(summaries):
                try:
                    data = json.loads(summaries[step].content)
                    entries.append(data)
                except Exception:
                    pass
            else:
                break

        if entries:
            history = ""
            for hour in entries:
                for key in hour:
                    history += f"{key}: {hour[key]}\n"
    finally:
        session.close()

    lsum = summarize(lstring, history=history)

    # Generate timestamp for entry key
    timestamp = int(datetime.datetime.utcnow().timestamp())

    if not isinstance(lsum, str):
        # WARNING: missing transcript. This only matters if we have a CHATGPT KEY set.
        return

    # for leach in re.findall(r'({.+?\})',lsum):
    # if we don't find this, then we wasted money...
    lsuc = False
    session = SessionLocal()
    for leach in re.findall(
        r"^\s*?`?`?`?j?s?o?n?\n?(\{.+?\})\n?`?`?`?",
        lsum,
        flags=re.DOTALL,
    ):
        try:
            session.add(Summary(timestamp=timestamp, content=leach))
            session.commit()
            lsuc = True
        except OperationalError as exc:
            logging.warning("Failed to persist summary: database unavailable: %s", exc)
            session.rollback()
            break
        except Exception:
            session.rollback()
    session.close()
    if lsuc is False:
        logging.warning("MISSED CAPTION ($$$) %s", lsum)

    # Send alerts with the summary
    if lsuc:
        email_alert("LLM Summary Update", f"New summary generated:\n\n{lsum}")
        sms_alert("LLM Summary Update", f"New summary generated:\n\n{lsum}")


def schedule_summarization():
    """Run ``update_summary`` hourly without blocking the caller."""

    try:
        scheduler.add_job(
            func=update_summary,
            trigger=CronTrigger(minute=0),
            id="summary",
            replace_existing=True,
        )
        # queue an immediate one-off run so startup waits for nothing
        scheduler.add_job(
            func=update_summary,
            trigger="date",
            id="summary_init",
            replace_existing=True,
            run_date=datetime.datetime.now(),
        )
    except Exception as e:
        logging.error("job schedule error: %s", e)


def update_weather_brief() -> None:
    """Generate the local weather brief artifacts from current templates."""

    try:
        from app.utils.weather_brief import generate_weather_brief_artifacts

        generate_weather_brief_artifacts()
    except Exception as exc:
        logging.warning("Weather brief update failed: %s", exc)


def schedule_weather_brief() -> None:
    """Run the weather brief before normal morning dashboard checks."""

    try:
        scheduler.add_job(
            func=update_weather_brief,
            trigger=CronTrigger(hour="5,7", minute=30),
            id="weather_brief",
            replace_existing=True,
        )
    except Exception as e:
        logging.error("job schedule error: %s", e)


def update_seiche_brief() -> None:
    """Generate the Lake Michigan SeicheClock artifacts from NOAA data."""

    try:
        from app.utils.seiche_brief import generate_seiche_brief_artifacts

        generate_seiche_brief_artifacts()
    except Exception as exc:
        logging.warning("SeicheClock update failed: %s", exc)


def schedule_seiche_brief() -> None:
    """Keep SeicheClock reasonably fresh without hammering NOAA."""

    try:
        scheduler.add_job(
            func=update_seiche_brief,
            trigger=CronTrigger(minute="*/15"),
            id="seiche_brief",
            replace_existing=True,
        )
    except Exception as e:
        logging.error("job schedule error: %s", e)


def lcm(a: int, b: int) -> int:
    """Return least common multiple of ``a`` and ``b``."""

    return abs(a * b) // gcd(a, b) if a and b else 0


def _lcm_many(values) -> int:
    """Return the LCM of ``values`` using :func:`lcm`."""

    return reduce(lcm, values, 1)


def calculate_optimal_offsets(templates: dict, spread_minutes: int) -> dict:
    """Spread actual recurring starts within the startup window and interval.

    Do not scale phases from a longer simulation window: scaling destroys the
    collision checks and piles short-interval cameras onto the end of startup.
    Stable name-derived phases distribute ties, while recurring load checks
    avoid collisions with more frequent cameras already placed.
    """
    if not templates:
        return {}
    frequencies = {}
    for name, template in templates.items():
        try:
            frequencies[name] = max(60, 60 * int(template.get("frequency", 30)))
        except (TypeError, ValueError, OverflowError):
            frequencies[name] = 1800
    spread = max(1, min(86_400, int(spread_minutes) * 60))
    horizon = min(86_400, max(spread, _lcm_many(frequencies.values())))
    load = [0] * horizon
    offsets = {}
    # Place frequent work first so slower feeds can avoid all of its repeats.
    for name, frequency in sorted(
        frequencies.items(), key=lambda item: (item[1], item[0])
    ):
        limit = min(spread, frequency)
        preferred = (
            int.from_bytes(hashlib.sha256(name.encode()).digest()[:8], "big") % limit
        )
        best_offset = preferred
        best_count = float("inf")
        for distance in range(limit):
            offset = (preferred + distance) % limit
            count = sum(load[t] for t in range(offset, horizon, frequency))
            if count < best_count:
                best_count, best_offset = count, offset
            if count == 0:
                break
        for tick in range(best_offset, horizon, frequency):
            load[tick] += 1
        offsets[name] = best_offset
    return offsets


def _template_is_archived(template: dict | None) -> bool:
    """Return True when a template is intentionally kept out of active crawls."""

    groups = str((template or {}).get("groups") or "")
    return "archive" in {group.strip().lower() for group in groups.split(",")}


def camera_executor(template):
    """Keep camera admission/capture work out of the maintenance executor."""

    groups = {g.strip().lower() for g in str(template.get("groups") or "").split(",")}
    if "priority" in groups:
        return "priority_cameras"
    if str(template.get("browser") or "").lower() in {"1", "true", "on", "yes"}:
        return "browser_captures"
    return "camera_captures"


def _queued_browser_template(template: dict) -> bool:
    return str(template.get("browser") or "").lower() in {
        "1",
        "true",
        "on",
        "yes",
    } and "/integrations/google/webrtc/preview" not in str(template.get("url") or "")


def schedule_camera_capture(name: str, template: dict, timeout: int) -> None:
    """Enqueue browser work quickly; leave native capture workers independent."""
    current = get_template(name)
    if not current or _template_is_archived(current):
        return
    if _queued_browser_template(current):
        if current.get("source_template") == "hubitat_site_dashboard":
            return  # Site uploads are the sole capture producer for these views.
        if browser_queue.capture_is_current(current):
            return
        if not browser_queue.enqueue(name, current):
            logging.warning(
                "Browser queue full; deferring %s to next scheduled turn", name
            )
        return
    run_with_timeout(update_camera, (name, current), timeout)


def retry_browser_camera(name: str, token: str) -> str | None:
    """Capture current configuration and acknowledge only this queue lease."""
    if not browser_queue.owns_lease(name, token):
        return
    retry = True
    attempted = True
    try:
        template = get_template(name)
        if not template or _template_is_archived(template):
            retry = False
            return
        if browser_queue.satisfied(name, token, template):
            retry = False
            return
        result = update_camera(name, template)
        retry = result == CAPTURE_STALE_BROWSER_SLOT_BUSY
        attempted = not retry
        return result
    finally:
        browser_queue.finish(name, token, retry=retry, attempted=attempted)


def process_browser_queue() -> None:
    """Run one leased capture; expired leases recover skipped or killed workers."""
    if _shutdown_event.is_set():
        return
    turn = browser_queue.claim()
    if not turn:
        return
    retry, attempted = True, False
    try:
        # Resolve obsolete tickets before opening network probes or forking.
        template = get_template(turn["name"])
        if (
            not template
            or _template_is_archived(template)
            or template.get("source_template") == "hubitat_site_dashboard"
            or browser_queue.satisfied(turn["name"], turn["token"], template)
        ):
            retry = False
            return
        if not is_system_online():
            return
        started = time.monotonic()
        attempted = True
        completed = run_with_timeout(
            retry_browser_camera, (turn["name"], turn["token"]), 120
        )
        attempted = completed is not None
        logging.info(
            "Browser queue turn camera=%s worker=%s elapsed=%.2fs",
            turn["name"],
            "deferred" if completed is None else "ok" if completed else "failed",
            time.monotonic() - started,
        )
    finally:
        # Lookup/probe/worker errors must not reserve the sole queue slot until
        # its 150-second lease expires. Child acknowledgments and newer lease
        # tokens make this a no-op when ownership has already changed.
        browser_queue.finish(
            turn["name"], turn["token"], retry=retry, attempted=attempted
        )


def schedule_browser_queue() -> None:
    """Drain durable browser turns with one dedicated bounded worker."""
    # Recover already-contended views immediately, oldest saved capture first.
    # Existing persistent tickets keep their age and lease across restarts.
    templates = get_templates()
    for name, template in sorted(
        templates.items(),
        key=lambda item: str(item[1].get("last_screenshot_time") or ""),
    ):
        if (
            not _template_is_archived(template)
            and template.get("last_capture_message") == CAPTURE_STALE_BROWSER_SLOT_BUSY
        ):
            browser_queue.enqueue(name, template)
    scheduler.add_job(
        id="browser_retry_queue",
        func=process_browser_queue,
        trigger="interval",
        # Short handoffs avoid wasting browser capacity between captures.
        # One worker, admission checks and per-ticket backoff still apply.
        seconds=1,
        executor="browser_retries",
        max_instances=1,
        coalesce=True,
        replace_existing=True,
        misfire_grace_time=30,
    )


def schedule_crawlers():
    """
    Fetch templates and schedule them according to their frequency, then schedule
    ``init_crawl``. Startup jobs are staggered over ``CRAWLER_STARTUP_SPREAD``
    minutes to keep CPU usage low when many cameras are configured.
    """
    templates = get_templates()
    archived_template_names = {
        name for name, template in templates.items() if _template_is_archived(template)
    }

    # Remove crawler jobs for templates that no longer exist
    existing_jobs = {job.id for job in scheduler.get_jobs()}
    for job_id in existing_jobs:
        if job_id == "browser_retry_queue":
            continue
        if job_id not in templates or job_id in archived_template_names:
            try:
                scheduler.remove_job(job_id)
            except Exception:
                pass

    # Determine optimized startup offsets for each crawler
    active_templates = {
        name: template
        for name, template in templates.items()
        if name not in archived_template_names
    }
    offsets = calculate_optimal_offsets(active_templates, CRAWLER_STARTUP_SPREAD)

    # Shuffle templates so the same cameras don't always start first
    shuffled_templates = list(templates.items())
    random.shuffle(shuffled_templates)

    for id, template in shuffled_templates:
        name = template.get("name")
        if name is None or name == "":
            continue
        if name in archived_template_names:
            logging.debug("Skipping archived crawler template: %s", name)
            continue
        output_path = os.path.join(SCREENSHOT_DIRECTORY, name)
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        output_path = os.path.join(VIDEO_DIRECTORY, name)
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        # Convert frequency from minutes to seconds
        try:
            seconds = 60 * int(
                template.get("frequency", 30)
            )  # Default value is now dynamically retrieved
        except Exception as e:
            logging.error(f"Error determining frequency for {name}: {e}")
            seconds = 60 * 30  # Fallback to default value if there's an issue

        # In low-CPU mode, clamp very short capture intervals so workers
        # are less likely to overlap and thrash.
        if LOW_CPU_MODE and seconds < 120:
            logging.debug(
                "LOW_CPU_MODE: clamping '%s' interval from %ss to 120s",
                name,
                seconds,
            )
            seconds = 120

        # The APScheduler job calls run_with_timeout() and blocks while waiting
        # for the worker process. If we block nearly the entire interval, jobs
        # will frequently overlap and APScheduler will log noisy skip warnings.
        # Keep some slack so normal drift doesn't cause overlap.
        max_timeout = 60 if LOW_CPU_MODE else 120
        timeout_seconds = max(10, min(max_timeout, max(10, seconds - 5)))

        priority = "priority" in {
            group.strip().lower()
            for group in str(template.get("groups") or "").split(",")
        }

        # Look up the pre-calculated startup offset for this crawler
        offset_delay_seconds = offsets.get(name, 0)

        # Apply incremental delay plus a small jitter to avoid synchronized
        # retries when network/service recovers.
        jitter_seconds = (
            random.randint(0, CRAWLER_SCHEDULE_JITTER_SECONDS)
            if CRAWLER_SCHEDULE_JITTER_SECONDS > 0
            else 0
        )
        start_delay_seconds = offset_delay_seconds + jitter_seconds
        if priority:
            # Entrances should start within one capture interval after a restart.
            start_delay_seconds %= seconds

        try:
            scheduler.add_job(
                func=schedule_camera_capture,
                trigger="interval",
                seconds=seconds,
                start_date=datetime.datetime.now()
                + datetime.timedelta(seconds=start_delay_seconds),
                args=(name, template, timeout_seconds),
                id=name,
                executor=camera_executor(template),
                replace_existing=True,
                # Allow a few scheduler invocations while a previous run is
                # still waiting on a worker process; run_with_timeout() will
                # no-op when the template is already active.
                max_instances=1 if camera_executor(template) != "default" else 3,
                coalesce=True,
                misfire_grace_time=max(30, seconds),
            )

        except Exception as e:
            logging.error("job schedule error: %s", e)
            logging.error(f"Error scheduling job for {name}: {e}")

    # Schedule init_crawl to run once, slightly offset as well
    try:
        scheduler.add_job(
            func=run_with_timeout,
            trigger="date",
            run_date=datetime.datetime.now() + datetime.timedelta(minutes=3),
            args=(init_crawl, (), 300),
            id="init_crawl",
        )
    except Exception as e:
        logging.error(f"Error scheduling initial crawl: {e}")


def get_feed_status():  # noqa: PLR0912, PLR0915
    """Return a list of status dictionaries for each configured feed."""

    templates = get_templates()
    now = datetime.datetime.utcnow()
    feeds = []

    danger_enabled = get_setting("DANGER_MODE", "True") == "True"
    port_open = is_chrome_debug_port_open("127.0.0.1", 9222)
    user_idle = not check_user_activity(timeout=1)

    def _humanize(ts: str | None) -> str | None:
        """Return a short "time ago" string like "5m ago"."""
        if not ts:
            return None
        try:
            dt = datetime.datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
        except Exception:
            return ts

        diff = (now - dt).total_seconds()
        if diff < 0:
            return "in the future"
        intervals = (
            ("y", 31536000),
            ("mo", 2592000),
            ("d", 86400),
            ("h", 3600),
            ("m", 60),
            ("s", 1),
        )
        for short, seconds in intervals:
            count = int(diff // seconds)
            if count >= 1:
                return f"{count}{short} ago"
        return "just now"

    def _iso(ts: str | None) -> str | None:
        if not ts:
            return None
        try:
            dt = datetime.datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
            return dt.isoformat() + "Z"
        except Exception:
            return ts

    for name, template in templates.items():
        last_shot = template.get("last_screenshot_time")
        last_caption = template.get("last_caption_time")
        frequency = int(template.get("frequency", 0) or 0)
        capture_failed = template.get("capture_failed", False)
        offline_since = template.get("offline_since")
        shot_count = get_screenshot_count(name)
        video_count = get_video_count(name)
        storage = get_storage_usage(name)
        storage_bytes = get_storage_usage_bytes(name)
        llm_responses = get_llm_response_count(name)
        llm_cost = get_llm_cost_estimate(name)
        headless = bool(template.get("headless", True))
        stealth = bool(template.get("stealth", False))
        browser = bool(template.get("browser", False))

        if browser:
            camera_type = "browser"
        elif headless and stealth:
            camera_type = "headless-stealth"
        elif headless:
            camera_type = "headless"
        elif stealth:
            camera_type = "stealth"
        else:
            camera_type = "standard"

        camera_tooltip = {
            "browser": "Full browser",
            "headless-stealth": "Headless with stealth",
            "headless": "Headless",
            "stealth": "Stealth",
            "standard": "Standard",
        }[camera_type]

        status = "ok"
        tooltip_parts: list[str] = []
        if capture_failed or offline_since:
            status = "error"
        elif last_shot:
            try:
                shot_time = datetime.datetime.strptime(last_shot, "%Y-%m-%d %H:%M:%S")
                diff = (now - shot_time).total_seconds()
                if frequency and diff > frequency * 120:
                    status = "slow"
            except Exception:
                status = "error"
        else:
            status = "error"

        if capture_failed:
            tooltip_parts.append("Capture failed")
        if offline_since:
            tooltip_parts.append(f"Offline since {offline_since}")
        if status == "slow" and last_shot and frequency:
            try:
                shot_time = datetime.datetime.strptime(last_shot, "%Y-%m-%d %H:%M:%S")
                diff = int((now - shot_time).total_seconds())
                tooltip_parts.append(
                    f"Last shot {diff // 60}m ago; expected every {frequency}m"
                )
            except Exception:
                pass

        last_log = None
        if status != "ok":
            with log_cache_lock:
                for log in reversed(log_cache):
                    if name in log.get("message", ""):
                        last_log = f"{log['level']}: {log['message']}"
                        break
        if last_log:
            tooltip_parts.append(f"Last log: {last_log[:120]}")

        danger = bool(template.get("danger", False))
        danger_reason = None
        if danger:
            if not (danger_enabled and port_open):
                danger_reason = "disabled"
            elif not user_idle:
                danger_reason = "user"

        with active_jobs_lock:
            job = active_jobs.get(name)
            capturing = bool(job and job.is_alive())
            failures = job_failures.get(name, 0)
            backoff_remaining = max(0.0, job_backoff_until.get(name, 0) - time.time())
            circuit_remaining = max(
                0.0, job_circuit_open_until.get(name, 0) - time.time()
            )
            next_probe_remaining = max(
                0.0, job_circuit_next_probe.get(name, 0) - time.time()
            )

        if circuit_remaining > 0:
            if status != "error":
                status = "slow"
            tooltip_parts.append(
                f"Circuit cooldown {int(circuit_remaining)}s ({failures} fails, next probe {int(next_probe_remaining)}s)"
            )
        elif backoff_remaining > 0:
            if status == "ok":
                status = "slow"
            tooltip_parts.append(
                f"Retry backoff {int(backoff_remaining)}s ({failures} fails)"
            )

        next_capture = None
        if frequency and last_shot:
            try:
                shot_dt = datetime.datetime.strptime(last_shot, "%Y-%m-%d %H:%M:%S")
                next_dt = shot_dt + datetime.timedelta(minutes=frequency)
                next_capture = next_dt.isoformat() + "Z"
            except Exception:
                pass

        tooltip = " | ".join(tooltip_parts) if tooltip_parts else "OK"

        feeds.append(
            {
                "name": name,
                "last_screenshot_time": _iso(last_shot),
                "last_screenshot_display": _humanize(last_shot),
                "last_caption_time": _iso(last_caption),
                "last_caption_display": _humanize(last_caption),
                "status": status,
                "tooltip": tooltip,
                "camera_type": camera_type,
                "camera_tooltip": camera_tooltip,
                "screenshot_count": shot_count,
                "video_count": video_count,
                "storage_usage": storage,
                "storage_usage_bytes": storage_bytes,
                "llm_response_count": llm_responses,
                "llm_cost_estimate": llm_cost,
                "danger": danger,
                "danger_reason": danger_reason,
                "capturing": capturing,
                "next_capture_time": next_capture,
                "frequency": frequency,
                "failure_count": failures,
                "retry_backoff_seconds": int(backoff_remaining),
                "circuit_cooldown_seconds": int(circuit_remaining),
                "circuit_next_probe_seconds": int(next_probe_remaining),
            }
        )

    feeds.sort(key=lambda f: f["name"])
    return feeds


def get_last_summary_time() -> str | None:
    """Return the timestamp of the most recent summary if available."""

    session = SessionLocal()
    try:
        record = session.query(Summary).order_by(Summary.timestamp.desc()).first()
        if record:
            return datetime.datetime.utcfromtimestamp(record.timestamp).strftime(
                "%Y-%m-%d %H:%M:%S"
            )
    except Exception:
        return None
    finally:
        session.close()
    return None


def summarize_recent_logs(limit: int = 200) -> str | None:
    """Summarize log entries from the last day using the LLM."""

    cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=1)
    with log_cache_lock:
        lines = [
            f"{e['level']} {e['message']}"
            for e in list(log_cache)[-limit:]
            if e.get("timestamp") and e["timestamp"] >= cutoff
        ]

    if not lines:
        return None

    text = "\n".join(lines)
    result = summarize(text)
    if result:
        ts = int(datetime.datetime.utcnow().timestamp())
        session = SessionLocal()
        try:
            session.add(LogSummary(timestamp=ts, content=result))
            session.commit()
        finally:
            session.close()
    return result


def get_or_generate_log_summary() -> str | None:
    """Return a recent log summary or generate one."""

    cutoff = int(
        (datetime.datetime.utcnow() - datetime.timedelta(hours=24)).timestamp()
    )
    session = SessionLocal()
    try:
        rec = session.query(LogSummary).order_by(LogSummary.timestamp.desc()).first()
        if rec and rec.timestamp >= cutoff:
            return rec.content
    finally:
        session.close()

    return summarize_recent_logs()


def get_top_failures(
    limit: int = 10, window_hours: int = 24
) -> list[dict[str, object]]:
    """Return the most frequent failure sources within the time window."""

    cutoff = datetime.datetime.utcnow() - datetime.timedelta(hours=window_hours)
    with log_cache_lock:
        recent_logs = [
            entry
            for entry in list(log_cache)
            if entry.get("timestamp") and entry["timestamp"] >= cutoff
        ]

    templates = get_templates()
    url_to_templates: dict[str, list[str]] = {}
    for name, template in templates.items():
        url = template.get("url") or ""
        if not url:
            continue
        clean_url = sanitize_url(url)
        url_to_templates.setdefault(clean_url, []).append(name)

    failures: dict[tuple[str, str, str], dict[str, object]] = {}
    for entry in recent_logs:
        message = entry.get("message", "")
        if not message:
            continue
        timestamp = entry.get("timestamp")
        if timestamp is None:
            continue

        name = None
        url = None
        reason = None

        if "Capture failed for " in message:
            idx = message.find("Capture failed for ")
            remainder = message[idx + len("Capture failed for ") :].strip()
            if remainder.endswith(")") and " (" in remainder:
                name_part, url_part = remainder.rsplit(" (", 1)
                name = name_part.strip()
                url = url_part[:-1].strip()
            else:
                name = remainder
            reason = "capture failed"
            if "[LAN_OFFLINE]" in message:
                reason = "capture failed (LAN offline)"
        elif message.startswith("RTSP preflight blocked "):
            remainder = message[len("RTSP preflight blocked ") :].strip()
            if remainder.endswith(")") and " (" in remainder:
                url_part, reason_part = remainder.rsplit(" (", 1)
                url = url_part.strip()
                reason = reason_part[:-1].strip()
            else:
                url = remainder
                reason = "rtsp preflight blocked"
        else:
            continue

        template_name = None
        display_name = name or url or "Unknown"
        if name and name in templates:
            template_name = name
        elif url:
            candidates = url_to_templates.get(url, [])
            if len(candidates) == 1:
                template_name = candidates[0]
                display_name = candidates[0]
            elif len(candidates) > 1:
                display_name = f"{candidates[0]} (+{len(candidates) - 1})"

        key = (display_name, reason or "unknown", url or "")
        if key in failures:
            failures[key]["count"] = int(failures[key]["count"]) + 1
            if timestamp > failures[key]["last_seen_dt"]:
                failures[key]["last_seen_dt"] = timestamp
        else:
            log_query = template_name or url or ""
            failures[key] = {
                "name": display_name,
                "template_name": template_name,
                "reason": reason or "unknown",
                "url": url,
                "log_query": log_query,
                "count": 1,
                "last_seen_dt": timestamp,
            }

    results = list(failures.values())
    results.sort(
        key=lambda item: (
            int(item["count"]),
            item["last_seen_dt"],
        ),
        reverse=True,
    )
    trimmed = results[:limit]
    for item in trimmed:
        ts = item.pop("last_seen_dt")
        item["last_seen"] = ts.strftime("%Y-%m-%d %H:%M:%S") if ts else ""
    return trimmed


def summarize_camera_logs(name: str, limit: int = 200) -> str | None:
    """Summarize recent logs mentioning ``name`` using the LLM."""

    ensure_column("log_summaries", "camera", "VARCHAR(255)", "''")

    cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=1)
    with log_cache_lock:
        lines = [
            f"{e['level']} {e['message']}"
            for e in list(log_cache)[-limit:]
            if e.get("timestamp")
            and e["timestamp"] >= cutoff
            and name in e.get("message", "")
        ]

    if not lines:
        return None

    text = "\n".join(lines)
    result = summarize(text)
    if result:
        ts = int(datetime.datetime.utcnow().timestamp())
        session = SessionLocal()
        try:
            session.add(LogSummary(timestamp=ts, camera=name, content=result))
            session.commit()
        finally:
            session.close()
    return result


def get_or_generate_camera_log_summary(name: str) -> str | None:
    """Return a recent log summary for ``name`` or generate one."""

    ensure_column("log_summaries", "camera", "VARCHAR(255)", "''")

    cutoff = int(
        (datetime.datetime.utcnow() - datetime.timedelta(hours=24)).timestamp()
    )
    session = SessionLocal()
    try:
        rec = (
            session.query(LogSummary)
            .filter_by(camera=name)
            .order_by(LogSummary.timestamp.desc())
            .first()
        )
        if rec and rec.timestamp >= cutoff:
            return rec.content
    finally:
        session.close()

    return summarize_camera_logs(name)


# Background discovery cache

discovery_cache = {
    "results": [],
    "timestamp": 0.0,
    "running": False,
    "error": None,
    "started": 0.0,
}


def run_discovery() -> None:
    """Run camera discovery and cache the results."""

    discovery_cache["running"] = True
    discovery_cache["error"] = None
    discovery_cache["started"] = time.time()
    try:
        discovery_cache["results"] = camera_discovery.discover_cameras()
        discovery_cache["timestamp"] = time.time()
    except Exception as e:  # pragma: no cover - network dependent
        logging.error("background discovery failed: %s", e)
        discovery_cache["error"] = str(e)
    finally:
        discovery_cache["running"] = False


def get_discovery_status(max_age: int = 3600) -> dict:
    """Return cached discovery status."""

    age = time.time() - discovery_cache["timestamp"]
    running_for = None
    if discovery_cache["running"]:
        running_for = time.time() - discovery_cache["started"]
    job = scheduler.get_job("background_discovery")
    next_run_in = None
    if job and job.next_run_time:
        next_run_in = (
            job.next_run_time - datetime.datetime.now(job.next_run_time.tzinfo)
        ).total_seconds()
    status = "stale"
    if discovery_cache["running"]:
        status = "running"
    elif discovery_cache["error"]:
        status = "error"
    elif discovery_cache["timestamp"] == 0:
        status = "none"
    elif age <= max_age:
        status = "ready"
    return {
        "status": status,
        "age": age,
        "running_for": running_for,
        "next_run_in": next_run_in,
        "results": discovery_cache["results"] if age <= max_age else [],
        "running": discovery_cache["running"],
        "error": discovery_cache["error"],
    }


def schedule_discovery() -> None:
    """Schedule periodic background discovery."""

    try:
        scheduler.add_job(
            func=run_discovery,
            trigger="interval",
            hours=1,
            id="background_discovery",
            replace_existing=True,
        )
        # kick off an immediate scan in the background
        scheduler.add_job(
            func=run_discovery,
            trigger="date",
            id="background_discovery_now",
            replace_existing=True,
            run_date=datetime.datetime.now(),
        )
    except Exception as e:
        logging.error("job schedule error: %s", e)


def stop_discovery() -> None:
    """Remove the scheduled background discovery job."""

    try:
        scheduler.remove_job("background_discovery")
    except Exception:
        pass


def process_offline_jobs() -> None:
    """Run any jobs queued while the system was offline."""

    if not is_system_online():
        return
    state = network_state()
    if not state.get("wan_ok", True) and not state.get("dns_ok", True):
        return
    if not _offline_jobs_run_lock.acquire(blocking=False):
        return

    session = SessionLocal()
    try:
        jobs = session.query(OfflineJob).order_by(OfflineJob.id).all()
        for job in jobs:
            try:
                job_id = job.id
            except ObjectDeletedError:
                # Job removed after query; skip it gracefully
                session.rollback()
                continue
            try:
                module_name, func_name = job.function.rsplit(".", 1)
                mod = importlib.import_module(module_name)
                func = getattr(mod, func_name)
                run_with_timeout(
                    func, args=tuple(json.loads(job.args)), timeout=job.timeout
                )
                session.delete(job)
                session.commit()
            except ObjectDeletedError:
                session.rollback()
                continue
            except Exception as exc:
                session.rollback()
                logging.error("Failed to run offline job %s: %s", job_id, exc)
    finally:
        session.close()
        try:
            _offline_jobs_run_lock.release()
        except RuntimeError:
            # Should not happen, but avoid taking down the scheduler thread.
            pass


def schedule_offline_job_processor() -> None:
    """Schedule periodic processing of queued offline jobs."""

    try:
        interval_seconds = 120 if LOW_CPU_MODE else 30
        scheduler.add_job(
            func=process_offline_jobs,
            trigger="interval",
            seconds=interval_seconds,
            id="process_offline_jobs",
            replace_existing=True,
            # Allow the scheduler thread to trigger again even if a previous run
            # is still working. process_offline_jobs() uses a non-blocking lock
            # to ensure only one worker is active at a time.
            max_instances=3,
            coalesce=True,
            misfire_grace_time=max(interval_seconds, 30),
        )
    except Exception as e:
        logging.error("job schedule error: %s", e)


def schedule_auto_update() -> None:
    """Schedule periodic auto-update checks."""

    if AUTO_UPDATE_BRANCH == "None":
        return
    try:
        scheduler.add_job(
            func=check_for_update,
            trigger="interval",
            hours=1,
            id="auto_update",
            replace_existing=True,
        )
    except Exception as e:
        logging.error("job schedule error: %s", e)


def refresh_clips() -> None:
    """Pre-generate short clips for each camera."""
    cameras = [
        name for name in os.listdir(VIDEO_DIRECTORY) if validate_template_name(name)
    ]

    if CLIP_REFRESH_MAX_CAMERAS and len(cameras) > CLIP_REFRESH_MAX_CAMERAS:
        logging.info(
            "Skipping clip refresh for %d cameras (limit %d)",
            len(cameras),
            CLIP_REFRESH_MAX_CAMERAS,
        )
        return

    base_url = f"http://127.0.0.1:{PORT}"
    for camera_name in cameras:
        try:
            requests.get(f"{base_url}/clip/{camera_name}", timeout=5)
        except Exception:
            logging.debug("clip refresh failed for %s", camera_name)


def schedule_clip_refresh() -> None:
    """Schedule periodic clip refresh jobs."""

    try:
        scheduler.add_job(
            func=refresh_clips,
            trigger="interval",
            minutes=5,
            id="refresh_clips",
            replace_existing=True,
        )
    except Exception as e:
        logging.error("job schedule error: %s", e)


def schedule_event_buffers() -> None:
    """Schedule low-rate LAN event-buffer captures."""

    if os.environ.get("PYTEST_CURRENT_TEST"):
        return
    try:
        from app.utils import event_buffer

        scheduler.add_job(
            func=event_buffer.tick_event_buffers,
            trigger="interval",
            seconds=1,
            id="event_buffers",
            replace_existing=True,
            executor="event_buffer",
            max_instances=2,
            coalesce=True,
            misfire_grace_time=5,
        )
    except Exception as e:
        logging.error("event buffer schedule error: %s", e)


def update_baselines(count: int = 10) -> None:
    """Generate baseline captions for each template."""

    templates = get_templates()
    for name in templates:
        shots = get_screenshots_for_template(name)
        if not shots:
            continue
        step = max(len(shots) // count, 1)
        selected = [shots[i] for i in range(0, len(shots), step)][:count]
        image_paths = [os.path.join(SCREENSHOT_DIRECTORY, name, s) for s in selected]
        caption = chatgpt_compare(
            "Describe the typical baseline view.",
            image_paths,
            template_name=name,
        )
        if caption:
            tmpl = get_template(name)
            tmpl["baseline_caption"] = caption
            save_template(name, tmpl)


def schedule_baseline_updates() -> None:
    """Run ``update_baselines`` once per day."""

    try:
        scheduler.add_job(
            func=update_baselines,
            trigger=CronTrigger(hour=0),
            id="baseline_update",
            replace_existing=True,
        )
    except Exception as e:
        logging.error("job schedule error: %s", e)
