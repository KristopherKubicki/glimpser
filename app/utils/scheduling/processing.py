from .helpers import *


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

            global clip_model, clip_processor

            if clip_model is None:
                clip_model = CLIPModel.from_pretrained(CLIP_MODEL_NAME)

            if clip_processor is None:
                clip_processor = CLIPProcessor.from_pretrained(CLIP_MODEL_NAME)

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
                    pass

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
