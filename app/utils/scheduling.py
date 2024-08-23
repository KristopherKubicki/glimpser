import datetime
import json
import logging
import os
import random
import re

from apscheduler.triggers.cron import CronTrigger
from dateutil import parser
from flask_apscheduler import APScheduler
from PIL import Image, ImageDraw, ImageFont
from transformers import CLIPProcessor, CLIPModel

from app.config import DEBUG, SCREENSHOT_DIRECTORY, SUMMARIES_DIRECTORY, VIDEO_DIRECTORY

from .detect import calculate_difference_fast
from .image_processing import chatgpt_compare
from .llm import summarize
from .screenshots import capture_or_download, remove_background, add_timestamp
from .template_manager import get_template, get_templates, save_template

scheduler = APScheduler()


clip_processor, clip_model = None, None


def find_closest_image(directory, last_caption_time):
    closest_image = None
    min_time_diff = None

    for filename in os.listdir(directory):
        if filename.endswith(".png") and "motion" in filename:
            # Extract timestamp from filename
            timestamp_str = filename.split("_")[0]
            try:
                timestamp = datetime.datetime.strptime(timestamp_str, "%Y%m%d%H%M%S")
                time_diff = abs(
                    last_caption_time - timestamp
                )  # todo.. can't go over...
                if min_time_diff is None or time_diff < min_time_diff:
                    closest_image = filename
                    min_time_diff = time_diff
            except ValueError:
                continue  # Skip files with unexpected filename format

    return closest_image


def add_motion_and_caption(image_path, caption=None, motion=False):
    if os.path.exists(image_path):

        if caption is None and motion is False:
            return

        try:
            with Image.open(
                image_path
            ) as image:  # consider unlinking if this fails to open
                # Convert the image to RGBA mode in case it's a format that doesn't support transparency
                try:
                    image = image.convert("RGB")
                except Exception as e:
                    # for debugging only, otherwise unlink the file
                    if DEBUG:
                        os.rename(image_path, image_path.replace(".png", ".broken"))
                    else:
                        # unlink the offending image
                        os.unlink(image_path)
                    print(" warning : image load issue:", image_path, e)
                    logging.error(f"Error saving image: {image_path} {e}")
                    return

                # Create an ImageDraw object
                draw = ImageDraw.Draw(image)
                max_height = min(image.height, image.width * 9 // 16)
                font_size = int(max_height * 0.05)
                top_offset = (image.height - max_height) / 2
                # if the image has the "invert" flag, then inverse this image for better readability

                try:
                    font = ImageFont.truetype("Arial.ttf", font_size)
                except IOError:
                    try:
                        font = ImageFont.truetype(
                            "LiberationSans-Regular.ttf", font_size
                        )
                    except IOError:
                        font = ImageFont.load_default()

                if motion is True:
                    motion_icon = "░"
                    # Calculate text size and position
                    text_w = int(draw.textlength(motion_icon, font=font))
                    text_h = font_size
                    x, y = int(image.width - text_w - 10), int(
                        image.height - int(font_size * 3) - top_offset
                    )
                    # Create a black transparent rectangle as the background
                    background = Image.new(
                        "RGBA", (text_w + 20, text_h + 10), (0, 0, 0, 64)
                    )  # 50% transparent black
                    image.paste(background, (x - 10, y - 5), background)
                    # Draw the timestamp in white text on the black transparent box
                    draw.text(
                        (x, y), motion_icon, font=font, fill=(255, 255, 255, 255)
                    )  # White text

                if caption is not None:
                    caption = caption[:64]
                    # Calculate text size and position
                    text_w = int(draw.textlength(caption, font=font))
                    text_h = font_size
                    x, y = int(10), int(image.height - int(font_size * 3) - top_offset)
                    # Create a black transparent rectangle as the background
                    background = Image.new(
                        "RGBA", (text_w + 20, text_h + 10), (0, 0, 0, 64)
                    )  # 50% transparent black
                    image.paste(background, (x - 10, y - 5), background)
                    # Draw the timestamp in white text on the black transparent box
                    draw.text(
                        (x, y), caption, font=font, fill=(255, 255, 255, 255)
                    )  # White text

                # Save the image
                image.save(image_path, "PNG")
        except Exception as e:
            logging.error(f"Error determining frequency for: {e}")


def calculate_sync_ratios(templates):
    """Calculate sync ratios for cameras based on their frequencies."""
    frequencies = {name: int(template.get('frequency', 30)) for name, template in templates.items()}
    min_frequency = min(frequencies.values())
    return {name: min_frequency / freq for name, freq in frequencies.items()}

def update_camera(name, template, image_file=None, sync_mode=False, sync_ratios=None):

    # just ignore the old
    template = get_template(name)

    if sync_mode and sync_ratios:
        # Adjust update frequency based on sync ratio
        adjusted_frequency = int(template.get('frequency', 30)) * sync_ratios[name]
        if random.random() > adjusted_frequency:
            return  # Skip update to maintain sync

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
                # TODO: add error mark from lerror
                add_timestamp(output_path, name, invert=template.get('invert',False))
                os.rename(output_path, output_path.replace(".tmp.png", ".png"))
                lsuc = True

    if lsuc is True:
        directory = os.path.join(SCREENSHOT_DIRECTORY, name)
        png_files = [
            f
            for f in os.listdir(directory)
            if f.endswith(".png") and os.path.isfile(os.path.join(directory, f))
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
            motion_config in [1, None]
            and (template.get("last_caption", "") or "") != ""
        ):
            return

        lsum = False
        percentage_difference = 0
        if len(png_files) > 1:
            percentage_difference = calculate_difference_fast(
                os.path.join(directory, png_files[-2]),
                os.path.join(directory, png_files[-1]),
            )
            if (percentage_difference or 0) >= float(template.get("motion", 0)):
                lsum = True

        elif png_files == 1:
            lsum = True

        prev_motion = os.path.join(directory, "last_motion.png")
        # print(" detected motion", lsum, name, template.get('last_caption'))

        allow = False

        #  Work through, Motion detection, then object detection, then live caption, then online captioning
        #
        last_caption_time, _last_motion_caption = None, None
        last_caption_trigger, last_motion_trigger = False, False

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

            global clip_model, clip_processor

            if clip_model is None:
                clip_model = CLIPModel.from_pretrained("openai/clip-vit-base-patch32")  # TODO: make these models configurable

            if clip_processor is None:
                clip_processor = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")

            # Load the latest image
            latest_image_path = os.path.join(directory, png_files[-1])
            image = Image.open(latest_image_path)

            # Process the image and text
            inputs = clip_processor(
                text=[object_filter], images=image, return_tensors="pt", padding=True
            )

            # Get the logits from the model
            outputs = clip_model(**inputs)
            logits_per_image = (
                outputs.logits_per_image
            )  # this is the image-text similarity score
            probs = logits_per_image.softmax(
                dim=1
            )  # we can take the softmax to get probabilities

            # Check if the object is detected with confidence higher than the threshold
            if probs[0, 0] >= object_confidence:
                allow = True
                # print(f"Object '{object_filter}' detected in {name} with confidence {probs[0, 0]}")

        if allow:

            # allow this to run one time if we have no detection
            #  generate the symlink. if there is a data/screenshots/<camera>/last_motion.png, please rename the move the symlink to prev_motion.png
            #    then, create the symlink for last_motion.png to point to the new png_files[-1]
            image_paths = []
            # add reference image if exists
            if os.path.exists(
                os.path.join(directory, "reference.png")
            ):  # if doesnt exist, consider taking the oldest?
                image_paths.append(os.path.join(directory, "reference.png"))

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
                        print("last caption....", closest_image_path)
                        image_paths.append(closest_image_path)
                except Exception as e:
                    print(" warning caption parsing error", e)
                    pass

            image_paths.append(os.path.join(directory, png_files[-1]))

            lctime = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

            # archictecture:
            #  check to see if there are any image in the object filter
            #  check to see if there are differences in the image
            #  check to see if there are alerts in the image -> no? use the llava caption
            #     yes?  use the gpt caption
            #

            #  add python llava (llama multimodal)  summarization.  Compare the reference frame, the previous motion capped frame, and this frame together.
            #      send llava the reference image (if available in data/screenshots/<camera>/reference.png), the last motion image (if available in data/screenshots/<camera>/last_motion.png)
            # TODO: be more targetted about this

            lret = None
            if last_motion_trigger:
                template["last_motion_time"] = lctime

            lret = None
            # just ignore the old
            template = get_template(name)

            if last_caption_trigger or template.get("last_caption") is None:
                lprompt = ""
                if template.get("notes"):
                    lprompt += " " + template["notes"]
                #  use Chatgpt_compare
                gret = chatgpt_compare(prompt=lprompt, image_paths=image_paths)
                # TODO: add a separator?
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
    templates = get_templates()  # Make sure to fetch the templates within this function
    for name, template in templates.items():
        update_camera(name, template)


def update_summary():

    # summarize all of htis together
    lstring = "The following are a list of real time dashboards and cameras, and their recent status updates:\n"
    templates = get_templates()  # Make sure to fetch the templates within this function

    # Sort templates by last_caption_time, descending order
    # TODO: this could just be a sql call instead
    sorted_templates = sorted(
        templates.items(),
        key=lambda item: item[1].get("last_caption_time", ""),
        reverse=True,
    )

    for id, template in sorted_templates:
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
                    print("error ", e, template)
                    print("NOTES:", fnotes)
                    print("GNTES:", fnotes)
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
    if True:
        # Specify the directory containing the .jl files
        directory = "data/summaries/"

        # Get all files in the directory
        files = os.listdir(directory)

        # Filter out only .jl files and sort them by last modified time in descending order
        jl_files = sorted(
            [file for file in files if file.endswith(".jl")],
            key=lambda x: os.path.getmtime(os.path.join(directory, x)),
            reverse=True,
        )
        print(jl_files)

        # for file in jl_files[:5]:
        entries = []
        steps = [1, 3, 8, 24]
        for step in steps:
            if step < len(jl_files):
                file = jl_files[step]
                file_path = os.path.join(directory, file)
                with open(file_path, "r") as f:
                    try:
                        data = json.load(f)
                        entries.append(data)
                    except Exception:
                        pass
            else:
                break  # or continue, depending on what you want to do when there aren't enough files

        if len(entries) > 0:
            history = ""
            for hour in entries:
                for key in hour:
                    history += "%s: %s\n" % (key, hour[key])

    lsum = summarize(lstring, history=history)

    # Generate timestamp for filename and entry key
    timestamp = datetime.datetime.utcnow().strftime("%Y%m%d%H%M%S")
    filename = f"data/summaries/{timestamp}.jl"

    if type(lsum) != str:
        print(" WARNING -- missing transcript")
        return

    # for leach in re.findall(r'({.+?\})',lsum):  # if we don't find this, then we wasted money...
    lsuc = False
    for leach in re.findall(
        r"^\s*?`?`?`?j?s?o?n?\n?(\{.+?\})\n?`?`?`?", lsum, flags=re.DOTALL
    ):  # if we don't find this, then we wasted money...
        # Write to file in JSONL format
        with open(filename, "w") as file:
            file.write(leach + "\n")
            lsuc = True
    if lsuc is False:
        print("WARNING MISSED CAPTION ($$$)", lsum)


def schedule_summarization():

    # loop through the templates and
    try:
        scheduler.add_job(
            func=update_summary,
            trigger=CronTrigger(minute=0),
            id="summary",
            replace_existing=True,
        )
    except Exception as e:
        print("job schedule error:", e)
    update_summary()


def schedule_crawlers():
    """
    Fetch templates and schedule them according to their frequency, and schedule init_crawl.
    Each job will be offset by an additional delay to avoid overloading the system.
    """
    templates = get_templates()
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

        # TODO: consider the fact that the tmeplate is out of date.
        # any time we update a camera, we upave to remove the old job and create a new one

        # Apply the incremental delay to space out job scheduling
        try:
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
        except Exception as e:
            print("job schedule error:", e)
            logging.error(f"Error scheduling job for {name}: {e}")

    # Schedule init_crawl to run once, slightly offset as well
    try:
        scheduler.add_job(
            func=init_crawl,
            trigger="date",
            run_date=datetime.datetime.now() + datetime.timedelta(minutes=3),
            id="init_crawl",
        )
    except Exception as e:
        logging.error(f"Error scheduling initial crawl: {e}")
