from .helpers import *
from importlib import import_module


def update_summary():

    # summarize all of htis together
    lstring = "The following are a list of real time dashboards and cameras, and their recent status updates:\n"
    templates = get_templates_sorted_by_last_caption_time()

    for id, template in templates:
        name = template.get("name")
        if "private" in template.get("groups", ""):
            continue
        if lstring.count("\n") > 50:
            break

        if template.get("last_caption_time"):
            caption_time = datetime.datetime.strptime(
                template.get("last_caption_time", ""), "%Y-%m-%d %H:%M:%S"
            )
            if (datetime.datetime.utcnow() - caption_time).total_seconds() > 3 * 3600:
                continue  # Skip templates older than 3 hours

            fnotes = re.split(
                r"\s*?(.+?[\?\!\.\,])(?: \s?|\t|$)",
                template.get("notes", "").strip(),
                flags=re.DOTALL,
            )
            gnotes = re.split(
                r"\s*?(.+?[\?\!\.\,])(?: \s?|\t|$)",
                template.get("last_caption", "").strip(),
                flags=re.DOTALL,
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
                    logging.debug("GNTES: %s", fnotes)
                    pass

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
        summaries = session.query(Summary).order_by(Summary.timestamp.desc()).all()
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

    if type(lsum) != str:
        # print(" WARNING -- missing transcript") # this only matters if we have a CHATGPT KEY set
        return

    # for leach in re.findall(r'({.+?\})',lsum):  # if we don't find this, then we wasted money...
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


def schedule_crawlers():
    """
    Fetch templates and schedule them according to their frequency, and schedule init_crawl.
    Each job will be offset by an additional delay to avoid overloading the system.
    """
    templates = get_templates()

    # Remove crawler jobs for templates that no longer exist
    existing_jobs = {job.id for job in scheduler.get_jobs()}
    for job_id in existing_jobs:
        if job_id not in templates:
            try:
                scheduler.remove_job(job_id)
            except Exception:
                pass

    total_crawlers = len(templates)
    base_delay = 60  # Base delay of 1 minute in seconds
    #  consider making this more dynamic, so that the shorter term ones have less of a base

    # shuffle the template so its not always the same ones
    shuffled_templates = list(templates.items())
    random.shuffle(shuffled_templates)

    for index, (id, template) in enumerate(shuffled_templates):
        name = template.get("name")
        if name is None or name == "":
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

        # Calculate the delay increment dynamically based on the total number of crawlers
        lbase_delay = base_delay
        if seconds > 120:
            lbase_delay *= 2
        if seconds > 240:
            lbase_delay *= 2
        if seconds > 360:
            lbase_delay *= 2
        if seconds > 720:
            lbase_delay *= 2

        delay_increment = lbase_delay / total_crawlers

        # Calculate the offset delay for this crawler
        offset_delay_seconds = index * delay_increment + index

        # Apply the incremental delay to space out job scheduling
        try:
            scheduler.add_job(
                func=run_with_timeout,
                trigger="interval",
                seconds=seconds,
                start_date=datetime.datetime.now()
                + datetime.timedelta(seconds=offset_delay_seconds),
                args=(update_camera, (name, template), seconds - 1),
                id=name,
                replace_existing=True,
            )

            """
            scheduler.add_job(
                func=update_camera,
                trigger="interval",
                seconds=seconds,
                start_date=datetime.datetime.now()
                + datetime.timedelta(seconds=offset_delay_seconds),
                args=[name, template],
                id=name,
                replace_existing=True,
            )
            """
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
        """
        scheduler.add_job(
            func=init_crawl,
            trigger="date",
            run_date=datetime.datetime.now() + datetime.timedelta(minutes=3),
            id="init_crawl",
        )
        """
    except Exception as e:
        logging.error(f"Error scheduling initial crawl: {e}")


system_metrics = {
    "cpu_usage": 0.0,
    "memory_usage": 0.0,
    "thread_count": 0,
    "start_time": time.time(),
}


stop_event = threading.Event()
metrics_thread = None
log_caching_thread = None


def ffmpeg_version() -> str:
    """Return the installed FFmpeg version or 'unavailable'."""
    try:
        output = subprocess.check_output(
            [FFMPEG_PATH, "-version"], stderr=subprocess.STDOUT, timeout=2
        ).decode()
        first = output.splitlines()[0]
        match = re.search(r"ffmpeg version\s+([^\s]+)", first)
        return match.group(1) if match else first
    except Exception:
        return "unavailable"


def machine_supports_hwaccel() -> bool:
    """Return ``True`` if GPU devices appear to be available."""
    return os.path.exists("/dev/dri") or shutil.which("nvidia-smi") is not None


def ffmpeg_supports_hwaccel() -> bool:
    """Return ``True`` if ``ffmpeg`` reports any hardware acceleration methods."""
    try:
        output = subprocess.check_output(
            [FFMPEG_PATH, "-hwaccels"], stderr=subprocess.STDOUT, timeout=2
        ).decode()
        lines = [l.strip() for l in output.splitlines() if l.strip()]
        return len(lines) > 1
    except Exception:
        return False


def collect_system_metrics():
    while not stop_event.is_set():
        system_metrics["cpu_usage"] = psutil.cpu_percent(interval=1)
        system_metrics["memory_usage"] = psutil.virtual_memory().percent
        system_metrics["thread_count"] = threading.active_count()
        time.sleep(5)  # Collect metrics every 5 seconds


def start_metrics_collection():
    global metrics_thread
    metrics_thread = threading.Thread(target=collect_system_metrics, daemon=True)
    metrics_thread.start()


def get_system_metrics():
    sched = import_module("app.utils.scheduling")
    uptime = time.time() - system_metrics["start_time"]
    psutil_mod = sched.psutil
    disk_usage = psutil_mod.disk_usage("/").percent
    open_files = len(psutil_mod.Process().open_files())
    return {
        "cpu_usage": round(system_metrics["cpu_usage"], 1),
        "memory_usage": round(system_metrics["memory_usage"], 1),
        "disk_usage": round(disk_usage, 1),
        "open_files": open_files,
        "thread_count": system_metrics["thread_count"],
        "uptime": f"{int(uptime // 3600)}h {int((uptime % 3600) // 60)}m {int(uptime % 60)}s",
        "ffmpeg_version": sched.ffmpeg_version(),
        "machine_hwaccel": sched.machine_supports_hwaccel(),
        "ffmpeg_hwaccel": sched.ffmpeg_supports_hwaccel(),
        "hwaccel_enabled": bool(
            sched.FFMPEG_HWACCEL and sched.FFMPEG_HWACCEL.lower() != "false"
        ),
    }


log_cache = deque(maxlen=10000)  # Store last 10000 log entries
log_cache_lock = threading.Lock()


def cache_logs():
    log_file_path = LOGGING_PATH
    os.makedirs(os.path.dirname(log_file_path), exist_ok=True)
    open(log_file_path, "a").close()

    try:
        with open(log_file_path, "r") as file:
            file.seek(0, os.SEEK_END)  # Start at end of file
            while not stop_event.is_set():
                new_log = file.readline()
                if new_log:
                    with log_cache_lock:
                        truncated_log = (
                            new_log[:500] + "..." if len(new_log) > 500 else new_log
                        )
                        log_parts = truncated_log.strip().split(" - ", 3)
                        if len(log_parts) >= 4:
                            timestamp_str, log_level, log_source, log_message = (
                                log_parts
                            )
                            try:
                                timestamp = datetime.datetime.strptime(
                                    timestamp_str, "%Y-%m-%d %H:%M:%S,%f"
                                )
                                log_cache.append(
                                    {
                                        "timestamp": timestamp,
                                        "level": log_level,
                                        "source": log_source,
                                        "message": log_message,
                                    }
                                )
                            except ValueError:
                                continue  # Skip incorrect timestamp format
                else:
                    time.sleep(1)  # Sleep briefly to avoid high CPU usage
    except Exception as e:
        logging.error(f"Error in cache_logs: {e}")


def start_log_caching():
    global log_caching_thread
    log_caching_thread = threading.Thread(target=cache_logs, daemon=True)
    log_caching_thread.start()

    # No longer schedule cache_logs via the APScheduler.  The background thread
    # itself handles continuous log caching and avoids spawning additional
    # threads on scheduler restarts.


def stop_background_tasks() -> None:
    """Signal background threads to exit and wait for them."""
    stop_event.set()
    for t in (metrics_thread, log_caching_thread):
        if t is not None:
            t.join(timeout=1)


def get_feed_status():
    """Return a list of status dictionaries for each configured feed."""

    templates = get_templates()
    now = datetime.datetime.utcnow()
    feeds = []

    def _humanize(ts: str | None) -> str | None:
        """Return a simple "time ago" string for the given timestamp."""
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
            ("year", 31536000),
            ("month", 2592000),
            ("day", 86400),
            ("hour", 3600),
            ("minute", 60),
            ("second", 1),
        )
        for label, seconds in intervals:
            count = int(diff // seconds)
            if count >= 1:
                return f"{count} {label}{'s' if count > 1 else ''} ago"
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
                    f"Last shot {diff // 60}m ago; expected every {frequency}s"
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
                "screenshot_count": shot_count,
                "video_count": video_count,
                "storage_usage": storage,
                "storage_usage_bytes": storage_bytes,
                "llm_response_count": llm_responses,
                "llm_cost_estimate": llm_cost,
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
