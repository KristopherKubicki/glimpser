from .helpers import *


def detect_background_color(image: Image.Image, sample_width: int = 10):
    """Return the most common color found along the image border."""
    arr = np.asarray(image.convert("RGBA"))
    top = arr[:sample_width, :, :].reshape(-1, 4)
    bottom = arr[-sample_width:, :, :].reshape(-1, 4)
    left = arr[:, :sample_width, :].reshape(-1, 4)
    right = arr[:, -sample_width:, :].reshape(-1, 4)
    border = np.concatenate([top, bottom, left, right], axis=0)
    colors, counts = np.unique(border, axis=0, return_counts=True)
    return tuple(int(c) for c in colors[counts.argmax()])


def remove_background(image, background_color=None, threshold=10):
    """Crop the image to remove the background color border and ensure a 16:9 aspect ratio."""
    if background_color is None:
        background_color = detect_background_color(image)
    # Find the bounding box of the non-background area
    bbox = find_bounding_box(image, background_color, threshold)

    # Adjust the bounding box to fit a 16:9 aspect ratio
    if bbox:
        bbox = adjust_bbox_to_aspect_ratio(bbox, image.size, aspect_ratio=(16, 9))
        image = image.crop(bbox)
    return image


def find_bounding_box(
    image: Image.Image,
    background_color=(14, 14, 14, 255),
    threshold: int = 10,
):
    """
    Return (left, top, right, bottom) that contains all pixels whose
    per-channel distance from `background_color` > threshold.

    If *every* pixel is background, returns None.
    """
    # RGBA → ndarray(H, W, 4)
    arr = np.asarray(image.convert("RGBA"), dtype=np.int16)

    bg = np.array(background_color, dtype=np.int16)
    # True where *any* channel differs more than threshold
    fg_mask = np.any(np.abs(arr - bg) > threshold, axis=-1)

    if not fg_mask.any():  # all background
        return None

    ys, xs = np.nonzero(fg_mask)
    top, bottom = ys.min(), ys.max()
    left, right = xs.min(), xs.max()

    return int(left), int(top), int(right), int(bottom)


def adjust_bbox_to_aspect_ratio(bbox, image_size, aspect_ratio=(16, 9)):
    """Adjust the bounding box to fit the specified aspect ratio."""
    left, top, right, bottom = bbox
    bbox_width = right - left
    bbox_height = bottom - top
    if bbox_height == 0:
        bbox_height = 1

    bbox_aspect_ratio = bbox_width / bbox_height

    target_aspect_ratio = aspect_ratio[0] / aspect_ratio[1]

    if bbox_aspect_ratio > target_aspect_ratio:
        # The bounding box is too wide, adjust the height
        new_height = bbox_width / target_aspect_ratio
        vertical_padding = (new_height - bbox_height) / 2
        top = max(0, top - vertical_padding)
        bottom = min(image_size[1], bottom + vertical_padding)
    elif bbox_aspect_ratio < target_aspect_ratio:
        # The bounding box is too tall, adjust the width
        new_width = bbox_height * target_aspect_ratio
        horizontal_padding = (new_width - bbox_width) / 2
        left = max(0, left - horizontal_padding)
        right = min(image_size[0], right + horizontal_padding)

    return (int(left), int(top), int(right), int(bottom))


def is_similar_color(color1, color2, threshold):
    """Check if two colors are similar."""
    return all(abs(c1 - c2) <= threshold for c1, c2 in zip(color1, color2))


def is_mostly_blank(
    image: Image.Image,
    threshold: float = 0.98,
    blank_color=(255, 255, 255),
    text_std_threshold: int = 20,
    dark_threshold: int = 10,
):
    """
    True  → we consider the frame “uninteresting” (blank / flat / too dark).
    False → keep the frame.
    """
    arr = np.asarray(image.convert("RGB"), dtype=np.int16)

    # ---------- 1.  “Mostly blank?”  ----------
    blank = np.array(blank_color, dtype=np.int16)
    blank_px = np.all(np.abs(arr - blank) <= 30, axis=-1).mean()
    if blank_px >= threshold:
        return True

    # ---------- 2.  “Flat image?”  ----------
    # Low global std-dev ≈ little structure / shapes
    if arr.std() < text_std_threshold:
        return True

    # ---------- 3.  “Too dark?”  ----------
    # Use perceptual luma so pure-dark blue isn’t mis-treated
    luma = np.dot(arr.mean(axis=(0, 1)), [0.2126, 0.7152, 0.0722])
    if luma < dark_threshold:
        return True

    return False


def run_cmd(cmd, timeout):
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()  # SIGKILL
        out, err = proc.communicate()
        raise RuntimeError(f"timeout: {' '.join(cmd)}")
    if proc.returncode:
        raise RuntimeError(err.decode()[:300])
    return out


def add_timestamp(image_path, name="unknown", invert=False):
    if os.path.exists(image_path):
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
                # print(" warning : image load issue:", image_path, e)
                logging.error(f"Error saving image: {image_path} {e}")
                return

            draw = ImageDraw.Draw(image)
            # If the image has the "invert" flag, then invert colors for readability
            if invert:
                image = ImageOps.invert(image)

            # Define the timestamp format

            zone = tz.gettz(TZ) or tz.UTC  # fall back if the name is invalid
            local_time = datetime.datetime.now(zone)
            tz_name = local_time.tzname() or ""
            timestamp = local_time.strftime("%Y-%m-%d %H:%M:%S")
            if tz_name:
                timestamp = f"{timestamp} {tz_name}"

            utc_time = datetime.datetime.utcnow()
            utc_timestamp = utc_time.strftime("%Y-%m-%d %H:%M:%S UTC")

            max_height = min(image.height, image.width * 9 // 16)
            font_size = int(max_height * 0.05)
            if font_size < 5:  # ignore tiny images
                return

            top_offset = (image.height - max_height) / 2

            # Use the helper to load fonts. The small font is half-sized.
            font = load_font(font_size)
            font_small = load_font(int(max(5, font_size / 2)))

            padding = 6

            # Render the name in the upper-left corner
            x = padding
            y = int(padding + top_offset)
            bbox = draw.textbbox((x, y), name, font=font, stroke_width=1)
            text_w = bbox[2] - bbox[0]
            text_h = bbox[3] - bbox[1]
            background = Image.new(
                "RGBA",
                (text_w + padding * 2, text_h + padding * 2),
                (0, 0, 0, 128),
            )
            image.paste(background, (x - padding, y - padding), background)
            draw.text(
                (x, y),
                name,
                font=font,
                fill=(255, 255, 255, 255),
                stroke_width=1,
                stroke_fill=(0, 0, 0, 255),
            )

            # Timestamp in the lower-right corner
            text_w = draw.textbbox((0, 0), timestamp, font=font, stroke_width=1)[2]
            x = image.width - text_w - padding
            y = int(image.height - top_offset - font_size * 2)
            bbox = draw.textbbox((x, y), timestamp, font=font, stroke_width=1)
            text_w = bbox[2] - bbox[0]
            text_h = bbox[3] - bbox[1]
            background = Image.new(
                "RGBA",
                (text_w + padding * 2, text_h + padding * 2),
                (0, 0, 0, 128),
            )
            image.paste(background, (bbox[0] - padding, bbox[1] - padding), background)

            draw.text(
                (x, y),
                timestamp,
                font=font,
                fill=(255, 255, 255, 255),
                stroke_width=1,
                stroke_fill=(0, 0, 0, 255),
            )

            if utc_timestamp != timestamp:
                tz_bbox = draw.textbbox(
                    (0, 0), utc_timestamp + "Z", font=font_small, stroke_width=1
                )
                text_w = tz_bbox[2] - tz_bbox[0]
                text_h = tz_bbox[3] - tz_bbox[1]
                background = Image.new(
                    "RGBA",
                    (text_w + padding * 2, text_h + padding * 2),
                    (0, 0, 0, 128),
                )
                tz_x = x
                tz_y = y + font_size + padding
                image.paste(
                    background,
                    (tz_x - padding, tz_y - padding),
                    background,
                )
                draw.text(
                    (tz_x, tz_y),
                    utc_timestamp + "Z",
                    font=font_small,
                    fill=(255, 255, 255, 255),
                    stroke_width=1,
                    stroke_fill=(0, 0, 0, 255),
                )

            # Save the image
            image.save(image_path, "PNG")

        try:
            from ..qrcode_overlay import add_micro_barcode

            add_micro_barcode(image_path, name)
        except Exception as e:  # pragma: no cover - overlay failures are non-critical
            logging.debug(f"Micro barcode overlay failed: {e}")


def create_placeholder(image_path, name="unknown"):
    """Generate a simple placeholder image with a timestamp."""
    img = Image.new("RGB", (640, 360), color="black")
    draw = ImageDraw.Draw(img)
    font = load_font(20)
    zone = tz.gettz(TZ) or tz.UTC
    timestamp = datetime.datetime.now(zone).strftime("%Y-%m-%d %H:%M:%S")
    text = f"{name}\n{timestamp}"
    draw.multiline_text((10, 10), text, fill=(255, 255, 255), font=font)
    img.save(image_path, "PNG")


def download_image(
    url,
    output_path,
    timeout=CAPTURE_TIMEOUT,
    name="unknown",
    invert=False,
    dark=False,
    stealth=False,
    proxy=None,
    username=None,
    password=None,
):
    """Attempt to download an image directly from the URL and convert it to PNG format.

    Args:
        url (str): Image URL.
        output_path (str): Where to save the PNG.
        timeout (int): Timeout in seconds.
        name (str): Friendly name for logging.
        invert (bool): If True, invert timestamp colors.
        dark (bool): Apply dark mode.
        stealth (bool): Use stealth user agent.
        proxy (str, optional): Proxy to use for the HTTP request.
    """

    proxy = validate_proxy(proxy)

    # ideally the timeout should be pretty high, its an image, and it could be real big
    if timeout < 10:
        timeout = 10

    response = None

    cached = get_cached_status_code(url)
    if cached is not None and cached != 200:
        logging.debug(f"Skipping {url} due to cached status {cached}")
        return False
    try:
        lua = UA
        if stealth:
            lua = random_user_agent()
        headers = {"user-agent": lua}
        proxies = {"http": proxy, "https": proxy} if proxy else None

        auth = get_auth(url, username, password)

        request_kwargs = dict(
            stream=True,
            timeout=(timeout, timeout * 3),
            verify=False,
            headers=headers,
            auth=auth,
        )
        if proxies:
            request_kwargs["proxies"] = proxies

        response = http_session().get(url, **request_kwargs)
        if response.status_code == 401 and auth is not None:
            auth = get_digest_auth(url, username, password)
            request_kwargs = dict(
                stream=True,
                timeout=(timeout, timeout * 3),
                verify=False,
                headers=headers,
                auth=auth,
            )
            if proxies:
                request_kwargs["proxies"] = proxies

            response = http_session().get(url, **request_kwargs)

        status = response.status_code
        set_cached_status_code(url, status)

        if status == 200:
            # Open the image directly from the response bytes
            image = Image.open(io.BytesIO(response.content))
            response.close()

            # Convert the image to RGBA mode in case it's a format that doesn't support transparency
            image = image.convert("RGB")
            image = remove_background(image)
            if dark:
                apply_dark_mode(image)

            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            tmp_path = output_path + ".tmp"

            # Save to a temporary file first so readers don't see partial data
            image.save(tmp_path, "PNG")
            if os.path.exists(tmp_path) and _is_valid_png(tmp_path):
                add_timestamp(tmp_path, name=name, invert=invert)
                os.replace(tmp_path, output_path)
                return True
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        else:
            response.close()
            logging.warning(f"Error downloading image: HTTP status code {status} {url}")
    except Exception as e:
        logging.error(f"Error downloading image: {e} {url} {timeout}")
        set_cached_status_code(url, 0)
    finally:
        if response is not None:
            response.close()  # Ensure the connection is closed

    return False


def download_pdf(
    url,
    output_path,
    timeout=CAPTURE_TIMEOUT,
    name="unknown",
    invert=False,
    dark=False,
    stealth=False,
    username=None,
    password=None,
):
    """
    Attempt to download the first page of a PDF from the URL and convert it to PNG format.
    """
    tmp_name = None  # path of the downloaded PDF
    lsuccess = False

    cached = get_cached_status_code(url)
    if cached is not None and cached != 200:
        logging.debug(f"Skipping PDF download for {url} due to cached status {cached}")
        return False

    if timeout < 10:
        timeout = 10

    try:
        # Download the PDF file
        lua = UA
        if stealth:
            lua = random_user_agent()

        headers = {"user-agent": lua}
        auth = get_auth(url, username, password)

        response = http_session().get(
            url,
            stream=True,
            timeout=timeout,
            verify=False,
            headers=headers,
            auth=auth,
            allow_redirects=True,
        )

        # Possibly re-try with DigestAuth if 401
        if response.status_code == 401 and auth is not None:
            auth = get_digest_auth(url, username, password)
            response = http_session().get(
                url,
                stream=True,
                timeout=timeout,
                verify=False,
                headers=headers,
                auth=auth,
                allow_redirects=True,
            )
        set_cached_status_code(url, response.status_code)

        if response.status_code != 200:
            logging.error(f"Error downloading PDF: HTTP {response.status_code}")
            return False

        # Save PDF to a temp file

        tmpdirname = f"/tmp/glimpser_{name}"
        os.makedirs(tmpdirname, exist_ok=True)
        if os.path.exists(tmpdirname):
            with open(os.path.join(tmpdirname, "file.pdf"), "wb") as tmp:
                tmp_name = tmp.name
                tmp.write(response.content)

        # Convert the first page to an image
        pages = convert_from_path(tmp_name, first_page=1, last_page=1)
        if not pages:
            logging.error("Error converting PDF to image: No pages found")
            return False

        image = pages[0].convert("RGB")
        image = remove_background(image)
        if dark:
            image = apply_dark_mode(image)

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        tmp_path = output_path + ".tmp"
        image.save(tmp_path, "PNG")

        if os.path.exists(tmp_path) and _is_valid_png(tmp_path):
            add_timestamp(tmp_path, name=name, invert=invert)
            os.replace(tmp_path, output_path)
            logging.debug(f"Successfully saved PDF page to {output_path}")
            lsuccess = True
        else:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        return lsuccess

    except Exception as e:
        logging.error(f"Error downloading PDF: {e}")
        set_cached_status_code(url, 0)
        return False

    finally:
        # Always remove leftover PDF, unless you specifically want to keep it
        if tmp_name and os.path.exists(tmp_name):
            try:
                os.remove(tmp_name)
            except OSError:
                pass


def is_enhanced(url):
    extractors = youtube_dl.extractor.gen_extractors()
    for e in extractors:
        if e.suitable(url) and e.IE_NAME != "generic":
            return True
    return False


def get_arp_output(ip_address, timeout):
    if platform.system() == "Windows":
        command = ["arp", "-a", ip_address]
    else:
        command = ["ip", "neigh", "show", ip_address]
    try:
        return subprocess.check_output(
            command, stderr=subprocess.STDOUT, timeout=timeout
        )
    except FileNotFoundError:
        return b""


def is_private_ip(ip_address):
    return ipaddress.ip_address(ip_address).is_private


def is_address_reachable(address, port=80, timeout=5):

    if port is None:
        port = 80

    if timeout < 3:
        timeout = 3

    try:
        # Resolve the domain name to an IP address
        ip_address = socket.gethostbyname(address)
        # print(f"{address} resolved to {ip_address}")
    except Exception:
        if address in ("google.com", "www.google.com"):
            return True
        return False

    # check the arp table, particularly if its an unroutable ip address
    if is_private_ip(ip_address):
        try:
            arp_entry = get_arp_output(ip_address, timeout).lower()
            if "no entry" in arp_entry.decode().lower():
                logging.warning("failing arp entry for %s", ip_address)
                return False
        except Exception as e:
            logging.warning("failure to arp %s", e)

    try:
        # Create a socket object
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        # Attempt to connect to the address on the specified port
        result = sock.connect_ex((ip_address, port))
        sock.close()
        if result == 0:
            # print(f"Successfully connected to {ip_address} on port {port}")
            # print(f"Failed to connect to {ip_address} on port {port}")

            return True
        if address in ("google.com", "www.google.com"):
            return True
        return False
    except Exception as e:
        logging.warning(f"Socket error: {e}")
        if address in ("google.com", "www.google.com"):
            return True

    return False


def parse_url(url):
    """Return the domain and port extracted from *url*.

    ``urllib.parse.urlparse`` treats strings without a scheme oddly.  For
    example ``"example.com:8080/path"`` is parsed with ``"example.com"`` as the
    *scheme* rather than the hostname.  To handle such URLs we prefix ``"//"`` so
    they are interpreted as network locations.
    """

    # Handle URLs missing a scheme like ``example.com:8080/path`` by prefixing
    # ``//`` which causes ``urlparse`` to parse the hostname and port correctly.
    if "://" not in url:
        parsed_url = urlparse("//" + url)
    else:
        parsed_url = urlparse(url)

    domain = parsed_url.hostname
    if parsed_url.scheme == "" and domain is None:
        domain = re.sub(r"\/.+?$", "", parsed_url.path)

    port = parsed_url.port
    # If the port is None and the scheme is specified, infer the default port.
    if port is None:
        if parsed_url.scheme == "http":
            port = 80
        elif parsed_url.scheme == "https":
            port = 443
        # Add more schemes and their default ports if necessary.

    return domain, port


def cas_error(url):

    entry = throttle_cache.setdefault(url, {"errors": 0, "first": time.time()})

    if entry.get("last", 0) > time.time() - 60 * 5:
        entry["errors"] += 1
    else:
        entry["errors"] = 1
        entry["first"] = time.time()
    entry["last"] = time.time()

    if entry["errors"] > 2:
        logging.error(f"Could not reach host: {url} {entry['errors']} times")
        entry["timeout"] = time.time() + 60 * 60  # 1 hour timeout
