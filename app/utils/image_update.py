"""Helpers for capturing images and applying motion/caption overlays."""

import datetime
import logging
import os
import re
from typing import Optional

from PIL import Image, ImageDraw, ImageFont
from dateutil import parser
from transformers import CLIPModel, CLIPProcessor

from app.config import DEBUG, SCREENSHOT_DIRECTORY
from .detect import calculate_difference_fast
from .image_processing import chatgpt_compare
from .screenshots import (
    capture_or_download,
    remove_background,
    add_timestamp,
    is_mostly_blank,
)
from .template_manager import get_template, save_template

clip_processor, clip_model = None, None


def find_closest_image(directory: str, last_caption_time: datetime.datetime) -> Optional[str]:
    """Return the filename of the image closest to *last_caption_time*."""
    closest_image = None
    min_time_diff = None
    for filename in os.listdir(directory):
        if filename.endswith(".png") and "motion" in filename:
            timestamp_str = filename.split("_")[0]
            try:
                timestamp = datetime.datetime.strptime(timestamp_str, "%Y%m%d%H%M%S")
                time_diff = abs(last_caption_time - timestamp)
                if min_time_diff is None or time_diff < min_time_diff:
                    closest_image = filename
                    min_time_diff = time_diff
            except ValueError:
                continue
    return closest_image


def add_motion_and_caption(image_path: str, caption: Optional[str] = None, motion: bool = False) -> None:
    """Overlay motion icon and caption text onto *image_path* if it exists."""
    if not os.path.exists(image_path):
        return

    if caption is None and not motion:
        return

    try:
        with Image.open(image_path) as image:
            try:
                image = image.convert("RGB")
            except Exception as e:
                if DEBUG:
                    os.rename(image_path, image_path.replace(".png", ".broken"))
                else:
                    os.unlink(image_path)
                logging.warning("image load issue: %s %s", image_path, e)
                logging.error("Error saving image: %s %s", image_path, e)
                return

            draw = ImageDraw.Draw(image)
            max_height = min(image.height, image.width * 9 // 16)
            font_size = int(max_height * 0.05)
            top_offset = (image.height - max_height) / 2

            try:
                font = ImageFont.truetype("Arial.ttf", font_size)
            except IOError:
                try:
                    font = ImageFont.truetype("LiberationSans-Regular.ttf", font_size)
                except IOError:
                    font = ImageFont.load_default()

            if motion:
                motion_icon = "░"
                text_w = int(draw.textlength(motion_icon, font=font))
                text_h = font_size
                x, y = int(image.width - text_w - 10), int(image.height - int(font_size * 3) - top_offset)
                background = Image.new("RGBA", (text_w + 20, text_h + 10), (0, 0, 0, 64))
                image.paste(background, (x - 10, y - 5), background)
                draw.text((x, y), motion_icon, font=font, fill=(255, 255, 255, 255))

            if caption is not None:
                caption = caption[:64].replace('\n', ' ')
                text_w = int(draw.textlength(caption, font=font))
                text_h = font_size
                x, y = int(10), int(image.height - int(font_size * 3) - top_offset)
                background = Image.new("RGBA", (text_w + 20, text_h + 10), (0, 0, 0, 64))
                image.paste(background, (x - 10, y - 5), background)
                draw.text((x, y), caption, font=font, fill=(255, 255, 255, 255))

            image.save(image_path, "PNG")
    except Exception as e:
        logging.error("Error updating image %s : %s", image_path, e)


def update_camera(name: str, template: dict, image_file: Optional[str] = None) -> None:
    """Capture or process a screenshot for *name* based on *template*."""
    template = get_template(name)

    lsuc = False
    if image_file is None:
        lsuc = capture_or_download(name, template)
    else:
        timestamp = datetime.datetime.utcnow().strftime("%Y%m%d%H%M%S")
        output_path = os.path.join(SCREENSHOT_DIRECTORY, f"{name}/{name}_{timestamp}.tmp.png")
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        if os.path.exists(output_path):
            image = Image.open(output_path)
            image = image.convert("RGB")
            image = remove_background(image)
            image.save(output_path, "PNG")
            if os.path.exists(output_path):
                add_timestamp(output_path, name, invert=template.get('invert', False))
                os.rename(output_path, output_path.replace(".tmp.png", ".png"))
                lsuc = True

    if lsuc:
        directory = os.path.join(SCREENSHOT_DIRECTORY, name)
        png_files = [
            f for f in os.listdir(directory) if f.endswith(".png") and os.path.isfile(os.path.join(directory, f))
        ]
        if not png_files:
            return
        png_files = sorted(png_files, key=lambda x: os.path.getctime(os.path.join(directory, x)))
        lpath = os.path.join(SCREENSHOT_DIRECTORY, "latest_camera.png")
        try:
            if os.path.exists(lpath + ".tmp"):
                os.unlink(os.path.abspath(lpath + ".tmp"))
            os.symlink(os.path.abspath(os.path.join("data/screenshots", name, png_files[-1])), os.path.abspath(lpath + ".tmp"))
            os.rename(os.path.abspath(lpath + ".tmp"), os.path.abspath(lpath))

            lpath = os.path.join(SCREENSHOT_DIRECTORY, name, "latest_camera.png")
            if os.path.exists(lpath + ".tmp"):
                os.unlink(os.path.abspath(lpath + ".tmp"))
            os.symlink(os.path.abspath(os.path.join("data/screenshots", name, png_files[-1])), os.path.abspath(lpath + ".tmp"))
            os.rename(os.path.abspath(lpath + ".tmp"), os.path.abspath(lpath))

            if "groups" in template:
                groups = template["groups"].split(",")
                for group in groups:
                    trimmed_group_name = group.strip()
                    group_lpath = os.path.join(SCREENSHOT_DIRECTORY, f"{trimmed_group_name}_latest_camera.png")
                    if os.path.exists(group_lpath + ".tmp"):
                        os.unlink(os.path.abspath(group_lpath + ".tmp"))
                    os.symlink(os.path.abspath(os.path.join("data/screenshots", name, png_files[-1])), os.path.abspath(group_lpath + ".tmp"))
                    os.rename(os.path.abspath(group_lpath + ".tmp"), os.path.abspath(group_lpath))
        except Exception:
            pass

        motion_config = template.get("motion", 1)
        if motion_config in [1, None] and (template.get("last_caption", "") or "") != "":
            return

        lsum = False
        latest_image_path = os.path.join(directory, png_files[-1])
        try:
            with Image.open(latest_image_path) as img:
                if is_mostly_blank(img):
                    logging.info("Skipping blank frame for motion detection: %s", latest_image_path)
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
        allow = False
        last_caption_time = None
        last_caption_trigger = False
        last_motion_trigger = False

        if (template.get("last_caption", "") or "") == "":
            allow = True
            last_caption_trigger = True
        if (template.get("last_motion_caption", "") or "") == "":
            allow = True
            last_motion_trigger = True
        if lsum:
            allow = True
            last_motion_trigger = True

        if not allow:
            try:
                last_motion_caption_time = datetime.datetime.strptime(
                    template.get("last_motion_caption_time", "1970-01-01 00:00:00"),
                    "%Y-%m-%d %H:%M:%S",
                )
                if last_motion_caption_time and datetime.datetime.utcnow() - last_motion_caption_time > datetime.timedelta(hours=3):
                    allow = True
                    last_motion_trigger = True
            except Exception:
                pass

            ldelta = 24
            if int(template.get("frequency", 30)) <= 30:
                ldelta = 8
            if int(template.get("frequency", 30)) <= 5:
                ldelta = 3

            if (template.get("livecaption", "") or "") == "true":
                lfreq = int(template.get("frequency", 30))
                ldelta = max(1, lfreq / 7)

            try:
                last_caption_time = datetime.datetime.strptime(
                    template.get("last_caption_time", "1970-01-01 00:00:00"),
                    "%Y-%m-%d %H:%M:%S",
                )
                if last_caption_time and datetime.datetime.utcnow() - last_caption_time > datetime.timedelta(hours=ldelta):
                    allow = True
                    last_caption_trigger = True
            except Exception:
                pass

        object_filter = template.get("object_filter", "")
        object_confidence = 0.5
        try:
            object_confidence = float(template.get("object_confidence", 0.5))
        except Exception:
            pass

        if allow and object_filter and object_confidence is not None:
            global clip_model, clip_processor
            if clip_model is None:
                clip_model = CLIPModel.from_pretrained("openai/clip-vit-base-patch32")
            if clip_processor is None:
                clip_processor = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")

            latest_image_path = os.path.join(directory, png_files[-1])
            image = Image.open(latest_image_path)
            inputs = clip_processor(text=[object_filter], images=image, return_tensors="pt", padding=True)
            outputs = clip_model(**inputs)
            logits_per_image = outputs.logits_per_image
            probs = logits_per_image.softmax(dim=1)
            if probs[0, 0] >= object_confidence:
                allow = True

        if allow:
            image_paths = []
            if os.path.exists(os.path.join(directory, "reference.png")):
                image_paths.append(os.path.join(directory, "reference.png"))
            if "last_caption_time" in template and template["last_caption_time"] != "":
                try:
                    last_caption_time = parser.parse(template["last_caption_time"])
                    closest_image_filename = find_closest_image(directory, last_caption_time)
                    if closest_image_filename:
                        closest_image_path = os.path.join(directory, closest_image_filename)
                        logging.debug("last caption.... %s", closest_image_path)
                        image_paths.append(closest_image_path)
                except Exception as e:
                    logging.warning("caption parsing error %s", e)
                    pass
            image_paths.append(os.path.join(directory, png_files[-1]))

            lctime = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

            lret = None
            if last_motion_trigger:
                template["last_motion_time"] = lctime

            template = get_template(name)

            if last_caption_trigger or template.get("last_caption") is None:
                lprompt = ""
                if template.get("notes"):
                    lprompt += " " + template["notes"]
                gret = chatgpt_compare(prompt=lprompt, image_paths=image_paths)
                if gret and re.findall(r"(?:sorry|cannot|can not)", gret):
                    template["last_ret"] = gret + "*"
                elif gret:
                    template["last_caption"] = gret
                template["last_caption_time"] = lctime
                add_motion_and_caption(lpath, caption=gret, motion=lsum)
            elif lret is not None:
                add_motion_and_caption(lpath, caption=lret, motion=lsum)
            else:
                lcap = template.get("last_caption", template.get("last_motion_caption", None))
                add_motion_and_caption(lpath, caption=lcap, motion=lsum)

            save_template(name, template)

            if last_motion_trigger or lsum:
                if os.path.exists(os.path.join(directory, "last_motion_caption.png.tmp")):
                    os.remove(os.path.join(directory, "last_motion_caption.png.tmp"))
                os.symlink(png_files[-1], os.path.join(directory, "last_motion_caption.png.tmp"))
                os.rename(os.path.join(directory, "last_motion_caption.png.tmp"), os.path.join(directory, "last_motion_caption.png"))

            if last_caption_trigger:
                if os.path.exists(os.path.join(directory, "last_caption.png.tmp")):
                    os.remove(os.path.join(directory, "last_caption.png.tmp"))
                os.symlink(png_files[-1], os.path.join(directory, "last_caption.png.tmp"))
                os.rename(os.path.join(directory, "last_caption.png.tmp"), os.path.join(directory, "last_caption.png"))

            if os.path.exists(prev_motion):
                destination = os.readlink(prev_motion)
                if os.path.exists(os.path.join(directory, "prev_motion.png.tmp")):
                    os.remove(os.path.join(directory, "prev_motion.png.tmp"))
                os.symlink(destination, os.path.join(directory, "prev_motion.png.tmp"))
                os.rename(os.path.join(directory, "prev_motion.png.tmp"), os.path.join(directory, "prev_motion.png"))
                image_paths.append(os.path.join(directory, "prev_motion.png"))
            if os.path.exists(os.path.join(directory, "last_motion.png.tmp")):
                os.remove(os.path.join(directory, "last_motion.png.tmp"))
            os.symlink(png_files[-1], os.path.join(directory, "last_motion.png.tmp"))
            os.rename(os.path.join(directory, "last_motion.png.tmp"), os.path.join(directory, "last_motion.png"))
        elif lsum:
            template = get_template(name)
            lcap = template.get("last_caption", template.get("last_motion_caption", None))
            add_motion_and_caption(lpath, caption=lcap, motion=lsum)
            lctime = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            template["last_motion_time"] = lctime
            save_template(name, template)

            if os.path.exists(prev_motion):
                destination = os.readlink(prev_motion)
                if os.path.exists(os.path.join(directory, "prev_motion.png.tmp")):
                    os.remove(os.path.join(directory, "prev_motion.png.tmp"))
                os.symlink(destination, os.path.join(directory, "prev_motion.png.tmp"))
                os.rename(os.path.join(directory, "prev_motion.png.tmp"), os.path.join(directory, "prev_motion.png"))
            if os.path.exists(os.path.join(directory, "last_motion.png.tmp")):
                os.remove(os.path.join(directory, "last_motion.png.tmp"))
            os.symlink(png_files[-1], os.path.join(directory, "last_motion.png.tmp"))
            os.rename(os.path.join(directory, "last_motion.png.tmp"), os.path.join(directory, "last_motion.png"))
        else:
            template = get_template(name)
            lcap = template.get("last_caption", template.get("last_motion_caption", None))
            add_motion_and_caption(lpath, caption=lcap, motion=lsum)
