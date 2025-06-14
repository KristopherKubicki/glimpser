# app/utils/scheduling.py

import datetime
import importlib
import json
import logging
import multiprocessing
import os
import random
import re
import select
import shutil
import subprocess
import textwrap
import threading
import time
from collections import deque
from functools import reduce
from math import gcd

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
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from dateutil import parser
from flask_apscheduler import APScheduler
from PIL import Image, ImageDraw


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


from app.config import (
    AUTO_UPDATE_BRANCH,
    CLIP_MODEL_NAME,
    CLIP_MODEL_PATH,
    CLIP_REFRESH_MAX_CAMERAS,
    CRAWLER_STARTUP_SPREAD,
    DEBUG,
    FFMPEG_HWACCEL,
    FFMPEG_PATH,
    LOGGING_PATH,
    PORT,
    SCREENSHOT_DIRECTORY,
    SUMMARIES_DIRECTORY,
    VIDEO_DIRECTORY,
    WATCHDOG_CPU_THRESHOLD,
    get_setting,
)
from app.models import OfflineJob, Summary
from app.utils.auto_update import check_for_update
from app.utils.db import SessionLocal

from . import camera_discovery
from .detect import calculate_difference_fast
from .email_alerts import email_alert
from .http_callbacks import send_http_callback
from .image_processing import chatgpt_compare
from .llm import summarize
from .network import is_system_online
from .screenshots import (
    add_timestamp,
    capture_or_download,
    cas_error,
    check_user_activity,
    is_chrome_debug_port_open,
    is_mostly_blank,
    load_font,
    remove_background,
    throttle_cache,
)
from .sms_alerts import sms_alert
from .template_manager import (
    get_llm_cost_estimate,
    get_llm_response_count,
    get_screenshot_count,
    get_storage_usage,
    get_storage_usage_bytes,
    get_template,
    get_templates,
    get_templates_sorted_by_last_caption_time,
    get_video_count,
    mark_offline,
    save_template,
    set_capture_failed,
    update_last_screenshot_time,
)
from .validators import validate_template_name

logging.getLogger("apscheduler").setLevel(logging.WARNING)

clip_processor, clip_session = None, None

# Track currently running jobs to avoid launching duplicates.
active_jobs: dict[str, multiprocessing.Process] = {}
active_jobs_lock = threading.Lock()
# Track failures and backoff time to slow down flapping jobs.
job_failures: dict[str, int] = {}
job_backoff_until: dict[str, float] = {}


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


def _run_target(func, args):
    """Wrapper to set process title before executing ``func``."""
    if setproctitle:
        title = getattr(func, "__name__", "job")
        if args and isinstance(args[0], str):
            title += f":{args[0]}"
        setproctitle(f"glimpser {title}")
    func(*args)


def run_with_timeout(func, args=(), timeout=300):
    """Run *func* in a separate process with a timeout.

    If the system appears offline or process creation fails, the job is skipped
    and the associated template is marked offline when possible.
    """

    if not is_system_online():
        logging.warning(
            "System offline, skipping job %s", getattr(func, "__name__", "unknown")
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

    cpu_level = psutil.cpu_percent(interval=0.0)
    if cpu_level > WATCHDOG_CPU_THRESHOLD:
        logging.info(
            "High CPU (%.1f%%); skipping job %s",
            cpu_level,
            getattr(func, "__name__", "job"),
        )
        return

    # Determine key for tracking active jobs. For camera updates the first
    # argument is the camera name; otherwise fall back to function name.
    key = getattr(func, "__name__", "job")
    if args and isinstance(args[0], str):
        key = args[0]

    try:
        with active_jobs_lock:
            now = time.time()
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
        return

    process.join(timeout)
    success = True
    if process.is_alive():
        process.terminate()
        process.join()
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
    elif process.exitcode and process.exitcode != 0:
        success = False

    with active_jobs_lock:
        active_jobs.pop(key, None)
        if success:
            job_failures.pop(key, None)
            job_backoff_until.pop(key, None)
        else:
            fails = job_failures.get(key, 0) + 1
            job_failures[key] = fails
            job_backoff_until[key] = time.time() + min(2**fails, 300)


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


def update_camera(name, template, image_file=None, motion=False):

    # just ignore the old
    template = get_template(name)

    lsuc = False
    if image_file is None:
        lsuc = capture_or_download(name, template)
    else:
        timestamp = datetime.datetime.utcnow().strftime("%Y%m%d%H%M%S")
        # Update the output_path format to include the timestamp
        output_path = os.path.join(
            SCREENSHOT_DIRECTORY, f"{name}/{name}_{timestamp}.tmp.png"
        )
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        if os.path.exists(output_path):
            image = Image.open(output_path)
            # Convert the image to RGBA mode in case it's a format that doesn't support transparency
            image = image.convert("RGB")
            image = remove_background(image)
            image.save(output_path, "PNG")
            if os.path.exists(output_path):
                add_timestamp(output_path, name, invert=template.get("invert", False))
                os.rename(output_path, output_path.replace(".tmp.png", ".png"))
                lsuc = True

    url = template.get("url")

    if lsuc is True:
        update_last_screenshot_time(name)
        set_capture_failed(name, False)
    else:
        entry = throttle_cache.get(url)
        if (
            entry
            and entry.get("errors", 0) >= 10
            and time.time() - entry.get("first", time.time()) > 60 * 60 * 24
        ):
            mark_offline(name)
        set_capture_failed(name, True)

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

        png_files = sorted(
            png_files, key=lambda x: os.path.getctime(os.path.join(directory, x))
        )

        # link for other processes to use
        lpath = os.path.join(SCREENSHOT_DIRECTORY, "latest_camera.png")

        try:
            if os.path.exists(lpath + ".tmp"):
                os.unlink(os.path.abspath(lpath + ".tmp"))
            os.symlink(
                os.path.abspath(os.path.join("data/screenshots", name, png_files[-1])),
                os.path.abspath(lpath + ".tmp"),
            )
            os.rename(os.path.abspath(lpath + ".tmp"), os.path.abspath(lpath))

            lpath = os.path.join(SCREENSHOT_DIRECTORY, name, "latest_camera.png")
            if os.path.exists(lpath + ".tmp"):
                os.unlink(os.path.abspath(lpath + ".tmp"))
            os.symlink(
                os.path.abspath(os.path.join("data/screenshots", name, png_files[-1])),
                os.path.abspath(lpath + ".tmp"),
            )
            os.rename(os.path.abspath(lpath + ".tmp"), os.path.abspath(lpath))

            # Create symlinks for each group
            if "groups" in template:
                groups = template["groups"].split(",")
                for group in groups:
                    trimmed_group_name = group.strip()
                    group_lpath = os.path.join(
                        SCREENSHOT_DIRECTORY, f"{trimmed_group_name}_latest_camera.png"
                    )
                    if os.path.exists(group_lpath + ".tmp"):
                        os.unlink(os.path.abspath(group_lpath + ".tmp"))
                    os.symlink(
                        os.path.abspath(
                            os.path.join("data/screenshots", name, png_files[-1])
                        ),
                        os.path.abspath(group_lpath + ".tmp"),
                    )
                    os.rename(
                        os.path.abspath(group_lpath + ".tmp"),
                        os.path.abspath(group_lpath),
                    )

        except Exception:
            pass

        motion_config = template.get("motion", 1)
        if (
            not motion
            and motion_config in [1, None]
            and (template.get("last_caption", "") or "") != ""
        ):
            return

        lsum = motion
        percentage_difference = 0

        latest_image_path = os.path.join(directory, png_files[-1])
        try:
            with Image.open(latest_image_path) as img:
                if is_mostly_blank(img):
                    logging.info(
                        "Skipping blank frame for motion detection: %s",
                        latest_image_path,
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

        prev_motion = os.path.join(directory, "last_motion.png")
        # print(" detected motion", lsum, name, template.get('last_caption'))

        allow = motion

        #  Work through, Motion detection, then object detection, then live caption, then online captioning
        #
        last_caption_time, _last_motion_caption = None, None
        last_caption_trigger, last_motion_trigger = motion, motion

        if (template.get("last_caption", "") or "") == "":
            allow = True
            last_caption_trigger = True
            # print("allowing from no caption", name)
        if (template.get("last_motion_caption", "") or "") == "":
            allow = True
            last_motion_trigger = True

        if lsum is True:
            allow = True
            last_motion_trigger = True

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
                    # print("allowing because of an old caption", name)
            except Exception:
                # print(" parse exception", e) #n1c
                pass

            # at least once a day.
            #  maybe at least once per every 8 frames
            #  no more frequent than hourly
            ldelta = 24
            if int(template.get("frequency", 30)) <= 30:
                ldelta = 8
            if int(template.get("frequency", 30)) <= 5:
                ldelta = 3

            if (
                template.get("livecaption", "") or ""
            ) == "true":  # spending extra money...
                lfreq = int(template.get("frequency", 30))
                ldelta = max(1, lfreq / 7)

            try:
                last_caption_time = datetime.datetime.strptime(
                    template.get("last_caption_time", "1970-01-01 00:00:00"),
                    "%Y-%m-%d %H:%M:%S",
                )
                if (
                    last_caption_time
                    and datetime.datetime.utcnow() - last_caption_time
                    > datetime.timedelta(hours=ldelta)
                ):  # one caption per day is fine otherwise...
                    allow = True
                    last_caption_trigger = True
                    # print("allowing from old caption", name)
            except Exception:
                # print(" parse exception", e) #n1c
                pass

        # Implement a filter using CLIP
        object_filter = template.get("object_filter", "")
        object_confidence = 0.5
        try:
            object_confidence = float(template.get("object_confidence", 0.5))
        except Exception:
            pass

        # run the object detect AFTER the motion detetor
        if allow is True and object_filter and object_confidence is not None:

            global clip_session, clip_processor

            # Prefer the lightweight ONNX backend when available
            use_onnx = ort is not None

            if use_onnx:
                if clip_session is None:
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
                        clip_session = ort.InferenceSession(
                            CLIP_MODEL_PATH, providers=providers
                        )
                    except TypeError:
                        # Some runtimes (or tests) may not accept the providers
                        # keyword. Fall back to default initialization.
                        clip_session = ort.InferenceSession(CLIP_MODEL_PATH)

                if clip_processor is None:
                    clip_processor = CLIPProcessor.from_pretrained(CLIP_MODEL_NAME)

                # Load the latest image
                latest_image_path = os.path.join(directory, png_files[-1])
                image = Image.open(latest_image_path)

                inputs = clip_processor(
                    text=[object_filter],
                    images=image,
                    return_tensors="np",
                    padding=True,
                )

                outputs = clip_session.run(
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
                # print(f"Object '{object_filter}' detected in {name} with confidence {probs[0, 0]}")

        if allow:

            # allow this to run one time if we have no detection
            #  generate the symlink. if there is a data/screenshots/<camera>/last_motion.png, please rename the move the symlink to prev_motion.png
            #    then, create the symlink for last_motion.png to point to the new png_files[-1]
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
            #  check to see if there are alerts in the image -> no? use the llava caption
            #     yes?  use the gpt caption
            #

            #  add python llava (llama multimodal)  summarization. Compare the
            #  reference frame, the previous motion frame and the current frame
            #  together so captions reflect meaningful changes.

            lret = None
            if last_motion_trigger:
                template["last_motion_time"] = lctime

            lret = None
            # just ignore the old
            template = get_template(name)

            if last_caption_trigger or template.get("last_caption") is None:
                lprompt = ""
                if template.get("notes"):
                    lprompt += template["notes"].strip() + "\n---\n"
                #  use Chatgpt_compare with notes separated for clarity
                gret = chatgpt_compare(lprompt, image_paths, template_name=name)
                # print("  oldgpt:", name, template.get('last_caption'))
                # print("  newgpt:", name, gret)
                if gret and re.findall(r"(?:sorry|cannot|can not)", gret):
                    template["last_ret"] = gret + "*"
                elif gret:
                    template["last_caption"] = gret
                template["last_caption_time"] = lctime
                add_motion_and_caption(lpath, caption=gret, motion=lsum)
            elif lret is not None:
                add_motion_and_caption(lpath, caption=lret, motion=lsum)
            else:
                lcap = template.get(
                    "last_caption", template.get("last_motion_caption", None)
                )
                add_motion_and_caption(lpath, caption=lcap, motion=lsum)

            save_template(name, template)
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
                if os.path.exists(
                    os.path.join(directory, "last_motion_caption.png.tmp")
                ):
                    os.remove(os.path.join(directory, "last_motion_caption.png.tmp"))
                os.symlink(
                    png_files[-1],
                    os.path.join(directory, "last_motion_caption.png.tmp"),
                )
                os.rename(
                    os.path.join(directory, "last_motion_caption.png.tmp"),
                    os.path.join(directory, "last_motion_caption.png"),
                )

            if last_caption_trigger:
                if os.path.exists(os.path.join(directory, "last_caption.png.tmp")):
                    os.remove(os.path.join(directory, "last_caption.png.tmp"))
                os.symlink(
                    png_files[-1], os.path.join(directory, "last_caption.png.tmp")
                )
                os.rename(
                    os.path.join(directory, "last_caption.png.tmp"),
                    os.path.join(directory, "last_caption.png"),
                )

            if os.path.exists(prev_motion):
                destination = os.readlink(prev_motion)
                if os.path.exists(os.path.join(directory, "prev_motion.png.tmp")):
                    os.remove(os.path.join(directory, "prev_motion.png.tmp"))
                os.symlink(destination, os.path.join(directory, "prev_motion.png.tmp"))
                os.rename(
                    os.path.join(directory, "prev_motion.png.tmp"),
                    os.path.join(directory, "prev_motion.png"),
                )
                image_paths.append(os.path.join(directory, "prev_motion.png"))
            if os.path.exists(os.path.join(directory, "last_motion.png.tmp")):
                os.remove(os.path.join(directory, "last_motion.png.tmp"))
            os.symlink(png_files[-1], os.path.join(directory, "last_motion.png.tmp"))
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
            save_template(name, template)
            if template.get("callback_url"):
                payload = {
                    "name": name,
                    "caption": template.get("last_caption"),
                    "timestamp": lctime,
                    "motion": True,
                }
                send_http_callback(template.get("callback_url"), "motion", payload)

            if os.path.exists(prev_motion):
                destination = os.readlink(prev_motion)
                if os.path.exists(os.path.join(directory, "prev_motion.png.tmp")):
                    os.remove(os.path.join(directory, "prev_motion.png.tmp"))
                os.symlink(destination, os.path.join(directory, "prev_motion.png.tmp"))
                os.rename(
                    os.path.join(directory, "prev_motion.png.tmp"),
                    os.path.join(directory, "prev_motion.png"),
                )
            if os.path.exists(os.path.join(directory, "last_motion.png.tmp")):
                os.remove(os.path.join(directory, "last_motion.png.tmp"))
            os.symlink(png_files[-1], os.path.join(directory, "last_motion.png.tmp"))
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
        update_camera(name, template)


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


def lcm(a: int, b: int) -> int:
    """Return least common multiple of ``a`` and ``b``."""

    return abs(a * b) // gcd(a, b) if a and b else 0


def _lcm_many(values) -> int:
    """Return the LCM of ``values`` using :func:`lcm`."""

    return reduce(lcm, values, 1)


def calculate_optimal_offsets(templates: dict, spread_minutes: int) -> dict:
    """Return startup offsets in seconds for each crawler.

    The algorithm spreads initial runs across ``spread_minutes`` by computing a
    window based on the LCM of crawler frequencies. Each crawler is then placed
    within that window at the least-loaded slot to minimize overlapping starts.
    """

    if not templates:
        return {}

    frequencies = {
        name: 60 * int(t.get("frequency", 30)) for name, t in templates.items()
    }
    window = max(_lcm_many(frequencies.values()), spread_minutes * 60)
    window = min(window, 86_400)  # cap at one day to keep arrays manageable
    step = window // max(len(frequencies), 1)
    load = [0] * window
    offsets = {}

    for name, freq in sorted(frequencies.items(), key=lambda x: x[1], reverse=True):
        best_offset = 0
        best_count = float("inf")
        for offset in range(0, window, step or 1):
            count = sum(load[t] for t in range(offset, window, freq))
            if count < best_count:
                best_count = count
                best_offset = offset
            if best_count == 0:
                break
        for t in range(best_offset, window, freq):
            load[t] += 1
        scaled = int(best_offset / window * spread_minutes * 60)
        offsets[name] = scaled

    return offsets


def schedule_crawlers():
    """
    Fetch templates and schedule them according to their frequency, then schedule
    ``init_crawl``. Startup jobs are staggered over ``CRAWLER_STARTUP_SPREAD``
    minutes to keep CPU usage low when many cameras are configured.
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

    # Determine optimized startup offsets for each crawler
    offsets = calculate_optimal_offsets(templates, CRAWLER_STARTUP_SPREAD)

    # Shuffle templates so the same cameras don't always start first
    shuffled_templates = list(templates.items())
    random.shuffle(shuffled_templates)

    for id, template in shuffled_templates:
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

        # Look up the pre-calculated startup offset for this crawler
        offset_delay_seconds = offsets.get(name, 0)

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


system_metrics = {
    "cpu_usage": 0.0,
    "memory_usage": 0.0,
    "thread_count": 0,
    "start_time": time.time(),
    "top_threads": [],
}


stop_event = threading.Event()
metrics_thread = None
log_caching_thread = None
thread_cpu_times = {}
last_thread_sample = time.time()
child_procs = []


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
    """Continuously update CPU and memory metrics."""
    # Prime psutil's CPU measurement to avoid blocking on the first call
    psutil.cpu_percent(interval=None)
    proc = psutil.Process()
    global thread_cpu_times, last_thread_sample, child_procs
    proc.cpu_percent(interval=None)
    child_procs = proc.children(recursive=True)
    for child in child_procs:
        try:
            child.cpu_percent(interval=None)
        except Exception:
            continue
    while not stop_event.is_set():
        start = time.time()
        # Non-blocking call since we primed above
        system_metrics["cpu_usage"] = psutil.cpu_percent(interval=None)
        system_metrics["memory_usage"] = psutil.virtual_memory().percent
        system_metrics["thread_count"] = threading.active_count()

        interval = start - last_thread_sample or 1
        current = {t.id: t.user_time + t.system_time for t in proc.threads()}
        usages = []
        for tid, ttime in current.items():
            prev = thread_cpu_times.get(tid, ttime)
            cpu = ((ttime - prev) / interval) * 100 / psutil.cpu_count()
            name = next(
                (t.name for t in threading.enumerate() if t.ident == tid),
                f"Thread {tid}",
            )
            usages.append({"id": tid, "name": name, "cpu": round(cpu, 1)})
        thread_cpu_times = current
        last_thread_sample = start
        for child in proc.children(recursive=True):
            try:
                cpu = child.cpu_percent(interval=None)
                cmd = child.cmdline()
                name = (
                    os.path.basename(cmd[0]) if cmd else os.path.basename(child.name())
                )
                if cpu:
                    usages.append({"id": child.pid, "name": name, "cpu": round(cpu, 1)})
            except Exception:
                continue
        usages.sort(key=lambda x: x["cpu"], reverse=True)
        system_metrics["top_threads"] = usages[:10]
        time.sleep(5)  # Collect metrics every 5 seconds


def start_metrics_collection():
    global metrics_thread
    metrics_thread = threading.Thread(target=collect_system_metrics, daemon=True)
    metrics_thread.start()


def get_system_metrics():
    uptime = time.time() - system_metrics["start_time"]
    disk_usage = psutil.disk_usage("/").percent
    open_files = len(psutil.Process().open_files())
    ffmpeg_path = shutil.which(FFMPEG_PATH) or FFMPEG_PATH
    ffmpeg_gpu_support = ffmpeg_supports_hwaccel()
    return {
        "cpu_usage": round(system_metrics["cpu_usage"], 1),
        "memory_usage": round(system_metrics["memory_usage"], 1),
        "disk_usage": round(disk_usage, 1),
        "open_files": open_files,
        "thread_count": system_metrics["thread_count"],
        "top_threads": system_metrics.get("top_threads", []),
        "uptime": f"{int(uptime // 3600)}h {int((uptime % 3600) // 60)}m {int(uptime % 60)}s",
        "ffmpeg_version": ffmpeg_version(),
        "ffmpeg_path": ffmpeg_path,
        "machine_hwaccel": machine_supports_hwaccel(),
        "ffmpeg_hwaccel": ffmpeg_gpu_support,
        "ffmpeg_gpu_support": ffmpeg_gpu_support,
        "hwaccel_enabled": bool(FFMPEG_HWACCEL and FFMPEG_HWACCEL.lower() != "false"),
        "gpu_support": machine_supports_hwaccel(),
        "ffmpeg_gpu_enabled": bool(
            FFMPEG_HWACCEL and FFMPEG_HWACCEL.lower() != "false"
        ),
        "danger_mode": get_setting("DANGER_MODE", "True") == "True",
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
                if not new_log:
                    # Avoid busy looping when no new log lines are written.
                    time.sleep(1)
                    # The file may have been truncated. Seek to end and retry.
                    file.seek(0, os.SEEK_END)
                    continue

                with log_cache_lock:
                    truncated_log = (
                        new_log[:500] + "..." if len(new_log) > 500 else new_log
                    )
                    log_parts = truncated_log.strip().split(" - ", 3)
                    if len(log_parts) >= 4:
                        timestamp_str, log_level, log_source, log_message = log_parts
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

        next_capture = None
        if frequency and last_shot:
            try:
                shot_dt = datetime.datetime.strptime(last_shot, "%Y-%m-%d %H:%M:%S")
                next_dt = shot_dt + datetime.timedelta(minutes=frequency)
                next_capture = next_dt.isoformat() + "Z"
            except Exception:
                pass

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


def process_offline_jobs() -> None:
    """Run any jobs queued while the system was offline."""

    if not is_system_online():
        return

    session = SessionLocal()
    try:
        jobs = session.query(OfflineJob).order_by(OfflineJob.id).all()
        for job in jobs:
            try:
                module_name, func_name = job.function.rsplit(".", 1)
                mod = importlib.import_module(module_name)
                func = getattr(mod, func_name)
                run_with_timeout(
                    func, args=tuple(json.loads(job.args)), timeout=job.timeout
                )
                session.delete(job)
                session.commit()
            except Exception as exc:
                session.rollback()
                logging.error("Failed to run offline job %s: %s", job.id, exc)
    finally:
        session.close()


def schedule_offline_job_processor() -> None:
    """Schedule periodic processing of queued offline jobs."""

    try:
        scheduler.add_job(
            func=process_offline_jobs,
            trigger="interval",
            seconds=30,
            id="process_offline_jobs",
            replace_existing=True,
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
