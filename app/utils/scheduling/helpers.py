# app/utils/scheduling.py

import datetime
import json
import logging
import os
import random
import re
import psutil
import threading
import time
import multiprocessing
from collections import deque
import subprocess
import shutil
import textwrap

from apscheduler.triggers.cron import CronTrigger
from dateutil import parser
from flask_apscheduler import APScheduler
from PIL import Image, ImageDraw, ImageFont
from transformers import CLIPProcessor, CLIPModel

from app.config import (
    DEBUG,
    SCREENSHOT_DIRECTORY,
    SUMMARIES_DIRECTORY,
    VIDEO_DIRECTORY,
    CLIP_MODEL_NAME,
    LOGGING_PATH,
    FFMPEG_PATH,
    FFMPEG_HWACCEL,
)
from app.utils.db import SessionLocal
from app.models import Summary
from ..network import is_system_online

from ..detect import calculate_difference_fast
from ..image_processing import chatgpt_compare
from ..llm import summarize
from ..screenshots import (
    capture_or_download,
    remove_background,
    add_timestamp,
    is_mostly_blank,
    throttle_cache,
    load_font,
)
from ..template_manager import (
    get_template,
    get_templates,
    get_templates_sorted_by_last_caption_time,
    save_template,
    update_last_screenshot_time,
    mark_offline,
    set_capture_failed,
    get_screenshot_count,
    get_video_count,
    get_storage_usage,
    get_storage_usage_bytes,
    get_llm_response_count,
    get_llm_cost_estimate,
)
from ..email_alerts import email_alert
from ..sms_alerts import sms_alert
from ..http_callbacks import send_http_callback
from .. import camera_discovery

from apscheduler.schedulers.background import BackgroundScheduler
from concurrent.futures import ProcessPoolExecutor, TimeoutError

logging.getLogger("apscheduler").setLevel(logging.WARNING)

clip_processor, clip_model = None, None


class GracefulAPScheduler(APScheduler):
    def __init__(self):
        super().__init__()
        self._scheduler = None
        self.set_scheduler(BackgroundScheduler())

    def set_scheduler(self, scheduler):
        self._scheduler = scheduler

    def shutdown(self, wait=True):
        try:
            if self.running:
                # Stop all running jobs
                for job in self._scheduler.get_jobs():
                    job.remove()

                # Shutdown the scheduler
                super().shutdown(wait)

                # Additional cleanup if needed
                self._scheduler = None
            else:
                logging.info("Scheduler is not running.")
        except Exception as e:
            logging.error(f"Error during scheduler shutdown: {e}")
        finally:
            logging.info("Scheduler shutdown complete.")


scheduler = GracefulAPScheduler()


from importlib import import_module


def run_with_timeout(func, args=(), timeout=300):
    """Run *func* in a separate process with a timeout.

    If the system appears offline or process creation fails, the job is skipped
    and the associated template is marked offline when possible.
    """

    if not import_module("app.utils.scheduling").is_system_online():
        logging.warning(
            "System offline, skipping job %s", getattr(func, "__name__", "unknown")
        )
        if args and isinstance(args[0], str):
            try:
                mark_offline(args[0])
            except Exception:
                pass
        return

    try:
        process = multiprocessing.Process(target=func, args=args)
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
        return

    process.join(timeout)
    if process.is_alive():
        process.terminate()
        process.join()
        logging.warning("Process terminated due to timeout")


MAX_IMAGE_TIME_DIFF = datetime.timedelta(minutes=5)


def find_closest_image(directory, last_caption_time, max_time_diff=MAX_IMAGE_TIME_DIFF):
    """Return the closest motion image not older than ``max_time_diff``."""
    closest_image = None
    min_time_diff = None

    for filename in os.listdir(directory):
        if (
            filename.endswith(".png")
            and "motion" in filename
            and not os.path.islink(os.path.join(directory, filename))
        ):
            # Extract timestamp from filename
            timestamp_str = filename.split("_")[0]
            try:
                timestamp = datetime.datetime.strptime(timestamp_str, "%Y%m%d%H%M%S")
                time_diff = abs(last_caption_time - timestamp)

                # Ignore images outside the allowed time window
                if time_diff > max_time_diff:
                    continue

                if min_time_diff is None or time_diff < min_time_diff:
                    closest_image = filename
                    min_time_diff = time_diff
            except ValueError:
                continue  # Skip files with unexpected filename format

    return closest_image


def load_image(image_path):
    """Return an RGB image or ``None`` if loading fails."""
    try:
        image = Image.open(image_path)
        return image.convert("RGB")
    except Exception as e:  # pragma: no cover - I/O errors are environment specific
        if DEBUG:
            os.rename(image_path, image_path.replace(".png", ".broken"))
        else:
            os.unlink(image_path)
        logging.warning("image load issue: %s %s", image_path, e)
        logging.error("Error saving image: %s %s", image_path, e)
        return None


def apply_motion_icon(image, draw, font, font_size, top_offset, padding=6):
    motion_icon = "░"
    text_w = int(draw.textlength(motion_icon, font=font))
    text_h = font_size
    x = int(image.width - text_w - 10)
    y = int(image.height - int(font_size * 3) - top_offset)
    background = Image.new(
        "RGBA",
        (text_w + padding * 2, text_h + padding * 2),
        (0, 0, 0, 128),
    )
    image.paste(background, (x - padding, y - padding), background)
    draw.text(
        (x, y),
        motion_icon,
        font=font,
        fill=(255, 255, 255, 255),
        stroke_width=1,
        stroke_fill=(0, 0, 0, 255),
    )


def apply_caption(image, draw, font, font_size, caption, top_offset, padding=6):
    caption = caption[:64].replace("\n", " ")
    wrapped = textwrap.fill(caption, width=32)
    x = padding
    y = int(image.height - int(font_size * 3) - top_offset)
    bbox = draw.multiline_textbbox((x, y), wrapped, font=font, stroke_width=1)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    background = Image.new(
        "RGBA",
        (text_w + padding * 2, text_h + padding * 2),
        (0, 0, 0, 128),
    )
    image.paste(background, (x - padding, y - padding), background)
    draw.multiline_text(
        (x, y),
        wrapped,
        font=font,
        fill=(255, 255, 255, 255),
        stroke_width=1,
        stroke_fill=(0, 0, 0, 255),
    )


def save_image(image, image_path):
    image.save(image_path, "PNG")
    image.close()


def add_motion_and_caption(image_path, caption=None, motion=False):
    if not os.path.exists(image_path):
        return

    if caption is None and not motion:
        return

    image = load_image(image_path)
    if image is None:
        return

    try:
        draw = ImageDraw.Draw(image)
        max_height = min(image.height, image.width * 9 // 16)
        font_size = int(max_height * 0.05)
        top_offset = (image.height - max_height) / 2

        # Use the same font loader as timestamps
        font = load_font(font_size)

        padding = 6

        if motion:
            apply_motion_icon(image, draw, font, font_size, top_offset, padding)

        if caption is not None:
            apply_caption(image, draw, font, font_size, caption, top_offset, padding)

        save_image(image, image_path)
    except Exception as e:  # pragma: no cover - unexpected errors
        logging.error(f"Error updating image {image_path} : {e}")
