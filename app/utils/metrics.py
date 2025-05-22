"""System metrics collection utilities."""

import threading
import time
import psutil

system_metrics = {
    'cpu_usage': 0.0,
    'memory_usage': 0.0,
    'thread_count': 0,
    'start_time': time.time()
}


def collect_system_metrics():
    """Continuously update CPU, memory and thread statistics."""
    while True:
        system_metrics['cpu_usage'] = psutil.cpu_percent(interval=1)
        system_metrics['memory_usage'] = psutil.virtual_memory().percent
        system_metrics['thread_count'] = threading.active_count()
        time.sleep(5)


def start_metrics_collection():
    """Start a background thread for metrics collection."""
    metrics_thread = threading.Thread(target=collect_system_metrics, daemon=True)
    metrics_thread.start()


def get_system_metrics():
    """Return a dictionary with summarized system metrics."""
    uptime = time.time() - system_metrics['start_time']
    disk_usage = psutil.disk_usage('/').percent
    open_files = len(psutil.Process().open_files())
    return {
        'cpu_usage': round(system_metrics['cpu_usage'], 1),
        'memory_usage': round(system_metrics['memory_usage'], 1),
        'disk_usage': round(disk_usage, 1),
        'open_files': open_files,
        'thread_count': system_metrics['thread_count'],
        'uptime': f"{int(uptime // 3600)}h {int((uptime % 3600) // 60)}m {int(uptime % 60)}s"
    }
