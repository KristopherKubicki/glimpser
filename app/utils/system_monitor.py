import psutil
import logging
from datetime import datetime

def monitor_system_resources():
    cpu_usage = psutil.cpu_percent()
    memory_usage = psutil.virtual_memory().percent
    disk_usage = psutil.disk_usage('/').percent
    
    timestamp = datetime.now().isoformat()
    
    log_message = f"[{timestamp}] CPU: {cpu_usage}%, Memory: {memory_usage}%, Disk: {disk_usage}%"
    
    if cpu_usage > 90 or memory_usage > 90 or disk_usage > 90:
        logging.warning(f"High resource usage detected! {log_message}")
    else:
        logging.info(log_message)

    return {
        "timestamp": timestamp,
        "cpu_usage": cpu_usage,
        "memory_usage": memory_usage,
        "disk_usage": disk_usage
    }

def check_critical_resources():
    resources = monitor_system_resources()
    
    if resources['cpu_usage'] > 95 or resources['memory_usage'] > 95 or resources['disk_usage'] > 95:
        logging.critical(f"Critical resource usage! CPU: {resources['cpu_usage']}%, Memory: {resources['memory_usage']}%, Disk: {resources['disk_usage']}%")
        return False
    
    return True