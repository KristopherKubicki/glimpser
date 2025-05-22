"""Scheduler utilities for managing APScheduler tasks and related helpers."""

import datetime
import logging
import os
import random
import multiprocessing
import re

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from flask_apscheduler import APScheduler

from app.config import SCREENSHOT_DIRECTORY, VIDEO_DIRECTORY, SUMMARIES_DIRECTORY
from .template_manager import get_templates, get_template, save_template
from .email_alerts import email_alert
from .image_update import update_camera
from .llm import summarize

logging.getLogger("apscheduler").setLevel(logging.WARNING)


class GracefulAPScheduler(APScheduler):
    """APScheduler subclass that cleans up running jobs on shutdown."""

    def __init__(self):
        super().__init__()
        self._scheduler = None
        self.set_scheduler(BackgroundScheduler())

    def set_scheduler(self, scheduler):
        self._scheduler = scheduler

    def shutdown(self, wait: bool = True):
        try:
            if self.running:
                for job in self._scheduler.get_jobs():
                    job.remove()
                super().shutdown(wait)
                self._scheduler = None
            else:
                logging.info("Scheduler is not running.")
        except Exception as e:
            logging.error("Error during scheduler shutdown: %s", e)
        finally:
            logging.info("Scheduler shutdown complete.")


scheduler = GracefulAPScheduler()


def run_with_timeout(func, args=(), timeout: int = 300):
    """Run *func* in a separate process enforcing a timeout."""
    process = multiprocessing.Process(target=func, args=args)
    process.start()
    process.join(timeout)
    if process.is_alive():
        process.terminate()
        process.join()
        logging.warning("Process terminated due to timeout")


def init_crawl():
    """Trigger an update for each configured template once."""
    templates = get_templates()
    for name, template in templates.items():
        update_camera(name, template)


def update_summary():
    """Build a short text summary of recent camera activity."""
    lstring = (
        "The following are a list of real time dashboards and cameras, and their recent status updates:\n"
    )
    templates = get_templates()

    sorted_templates = sorted(
        templates.items(),
        key=lambda item: item[1].get("last_caption_time", ""),
        reverse=True,
    )

    for _id, template in sorted_templates:
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
                continue
            lstring += (
                f"name: {name}\tgroups: {template.get('groups', '')}\tupdated: {template.get('last_caption_time', '')}\tprompt: {template.get('notes', '')}\tresponse: {template.get('last_caption', '')}\n"
            )

    output_path = SUMMARIES_DIRECTORY
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    history = None
    directory = "data/summaries/"
    if os.path.exists(directory):
        files = os.listdir(directory)
        jl_files = sorted(
            [f for f in files if f.endswith(".jl")],
            key=lambda x: os.path.getmtime(os.path.join(directory, x)),
            reverse=True,
        )
        entries = []
        for step in [1, 3, 8, 24]:
            if step < len(jl_files):
                file_path = os.path.join(directory, jl_files[step])
                with open(file_path, "r") as f:
                    try:
                        data = json.load(f)
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

    lsum = summarize(lstring, history=history)
    timestamp = datetime.datetime.utcnow().strftime("%Y%m%d%H%M%S")
    filename = f"data/summaries/{timestamp}.jl"

    if isinstance(lsum, str):
        lsuc = False
        for block in re.findall(r"^\s*?`?`?`?j?s?o?n?\n?(\{.+?\})\n?`?`?`?", lsum, flags=re.DOTALL):
            with open(filename, "w") as file:
                file.write(block + "\n")
                lsuc = True
        if not lsuc:
            logging.warning("MISSED CAPTION ($$$) %s", lsum)
        else:
            email_alert("LLM Summary Update", f"New summary generated:\n\n{lsum}")


def schedule_summarization():
    """Schedule periodic summarization jobs."""
    try:
        scheduler.add_job(
            func=update_summary,
            trigger=CronTrigger(minute=0),
            id="summary",
            replace_existing=True,
        )
    except Exception as e:
        logging.error("job schedule error: %s", e)
    update_summary()


def schedule_crawlers():
    """Schedule crawler jobs for each template."""
    templates = get_templates()
    total_crawlers = len(templates)
    base_delay = 60

    shuffled_templates = list(templates.items())
    random.shuffle(shuffled_templates)

    for index, (id_, template) in enumerate(shuffled_templates):
        name = template.get("name")
        if not name:
            continue
        os.makedirs(os.path.join(SCREENSHOT_DIRECTORY, name), exist_ok=True)
        os.makedirs(os.path.join(VIDEO_DIRECTORY, name), exist_ok=True)

        try:
            seconds = 60 * int(template.get("frequency", 30))
        except Exception as e:
            logging.error("Error determining frequency for %s: %s", name, e)
            seconds = 60 * 30

        lbase_delay = base_delay
        for limit in [120, 240, 360, 720]:
            if seconds > limit:
                lbase_delay *= 2
        delay_increment = lbase_delay / total_crawlers
        offset_delay_seconds = index * delay_increment + index

        try:
            scheduler.add_job(
                func=run_with_timeout,
                trigger="interval",
                seconds=seconds,
                start_date=datetime.datetime.now() + datetime.timedelta(seconds=offset_delay_seconds),
                args=(update_camera, (name, template), seconds - 1),
                id=name,
                replace_existing=True,
            )
        except Exception as e:
            logging.error("job schedule error: %s", e)
            logging.error("Error scheduling job for %s: %s", name, e)

    try:
        scheduler.add_job(
            func=run_with_timeout,
            trigger="date",
            run_date=datetime.datetime.now() + datetime.timedelta(minutes=3),
            args=(init_crawl, (), 300),
            id="init_crawl",
        )
    except Exception as e:
        logging.error("Error scheduling initial crawl: %s", e)

