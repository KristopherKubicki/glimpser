"""Compatibility wrappers for scheduling utilities and log caching."""

import datetime
import logging
import os
import threading
import time
from collections import deque

from .scheduler import (
    GracefulAPScheduler,
    scheduler,
    run_with_timeout,
    init_crawl,
    update_summary,
    schedule_summarization,
    schedule_crawlers,
)
from .llm import summarize
from .metrics import (
    system_metrics,
    collect_system_metrics,
    start_metrics_collection,
    get_system_metrics,
)
from .image_update import (
    find_closest_image,
    add_motion_and_caption,
    update_camera,
    clip_processor,
    clip_model,
)
from .template_manager import get_templates

log_cache = deque(maxlen=10000)
log_cache_lock = threading.Lock()


def cache_logs():
    """Continuously read the log file into an in-memory cache."""
    log_file_path = "logs/glimpser.log"
    try:
        with open(log_file_path, "r") as file:
            file.seek(0, os.SEEK_END)
            while True:
                new_log = file.readline()
                if new_log:
                    with log_cache_lock:
                        truncated_log = new_log[:500] + '...' if len(new_log) > 500 else new_log
                        log_parts = truncated_log.strip().split(" - ", 3)
                        if len(log_parts) >= 4:
                            timestamp_str, log_level, log_source, log_message = log_parts
                            try:
                                timestamp = datetime.datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S,%f")
                                log_cache.append({
                                    "timestamp": timestamp,
                                    "level": log_level,
                                    "source": log_source,
                                    "message": log_message,
                                })
                            except ValueError:
                                continue
                else:
                    time.sleep(1)
    except Exception as e:
        logging.error(f"Error in cache_logs: {e}")


def start_log_caching():
    """Launch the background thread that caches log entries."""
    log_caching_thread = threading.Thread(target=cache_logs, daemon=True)
    log_caching_thread.start()
