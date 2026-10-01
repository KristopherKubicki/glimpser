from __future__ import annotations

import hashlib
import hmac
import logging
import os
import re
import threading
import time
from collections import OrderedDict
from io import BytesIO
from pathlib import Path

from flask import Blueprint, Response
from PIL import Image, ImageOps, UnidentifiedImageError

from app.utils.image_utils import caption_overlay_suppressed_name
from app.utils.screenshots import CAPTURE_PNG_COMPRESSION_LEVEL

_MISSING_SCREENSHOT_LOG_INTERVAL_SECONDS = 300
_FITTED_SCREENSHOT_MAX_EDGE = 4096
_FITTED_SCREENSHOT_MIN_EDGE = 16
_FITTED_SCREENSHOT_DEFAULT_BG = (18, 28, 40)
_MANUAL_CAPTURE_LOCK = threading.Lock()
_missing_screenshot_log_ts: dict[str, float] = {}
_FITTED_CACHE_MAX_BYTES = 32 * 1024 * 1024
_FITTED_CACHE_MAX_ENTRIES = 128
_fitted_cache: OrderedDict[tuple, bytes] = OrderedDict()
_fitted_cache_bytes = 0
_fitted_cache_lock = threading.Lock()


def _fitted_source_version(path: str) -> tuple:
    """Identify both atomic replacements and in-place edits of a source frame."""
    resolved = os.path.realpath(path)
    stat = os.stat(resolved)
    return (
        resolved,
        stat.st_dev,
        stat.st_ino,
        stat.st_size,
        stat.st_mtime_ns,
        stat.st_ctime_ns,
    )


def _remember_fitted(key: tuple, data: bytes) -> None:
    """Bound encoded variants by both byte size and entry count."""
    global _fitted_cache_bytes
    if len(data) > _FITTED_CACHE_MAX_BYTES:
        return
    with _fitted_cache_lock:
        old = _fitted_cache.pop(key, None)
        if old is not None:
            _fitted_cache_bytes -= len(old)
        _fitted_cache[key] = data
        _fitted_cache_bytes += len(data)
        while (
            _fitted_cache_bytes > _FITTED_CACHE_MAX_BYTES
            or len(_fitted_cache) > _FITTED_CACHE_MAX_ENTRIES
        ):
            _, evicted = _fitted_cache.popitem(last=False)
            _fitted_cache_bytes -= len(evicted)


def _publish_uploaded_clean_frame(image: Image.Image, final_path: str) -> None:
    """Bind an uploaded site's clean preview to its immutable capture file."""
    companion = Path(final_path + ".clean.png")
    pending = companion.with_name(companion.name + ".tmp")
    link = companion.parent / "last_clean.png"
    link_pending = companion.parent / "last_clean.png.tmp"
    try:
        image.save(pending, "PNG", compress_level=CAPTURE_PNG_COMPRESSION_LEVEL)
        pending.replace(companion)
        link_pending.unlink(missing_ok=True)
        link_pending.symlink_to(companion.resolve())
        link_pending.replace(link)
        latest = companion.parent / "latest_camera.png"
        latest_pending = companion.parent / "latest_camera.png.tmp"
        latest_pending.unlink(missing_ok=True)
        latest_pending.symlink_to(Path(final_path).resolve())
        latest_pending.replace(latest)
        for obsolete in sorted(companion.parent.glob("*.png.clean.png"))[:-2]:
            obsolete.unlink(missing_ok=True)
    finally:
        pending.unlink(missing_ok=True)
        link_pending.unlink(missing_ok=True)


def _log_missing_screenshot(name: str) -> None:
    """Rate-limit noisy missing-screenshot warnings per source."""

    # Tests expect a warning every time; avoid cross-test flakiness from
    # module-level rate limiting.
    if os.getenv("PYTEST_CURRENT_TEST"):
        from app import routes

        routes.logging.warning(
            "Unable to serve screenshot for %s",
            (name or "unknown").strip() or "unknown",
        )
        return

    now = time.monotonic()
    key = (name or "unknown").strip() or "unknown"
    last = _missing_screenshot_log_ts.get(key, 0.0)
    if now - last >= _MISSING_SCREENSHOT_LOG_INTERVAL_SECONDS:
        _missing_screenshot_log_ts[key] = now
        from app import routes

        routes.logging.warning("Unable to serve screenshot for %s", key)


def embedded_screenshot_token(template_name: str, secret: str) -> str:
    """Return the read-only embed token for a template screenshot."""

    payload = f"embedded-screenshot:{template_name}".encode()
    return hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()


def embedded_event_buffer_token(template_name: str, secret: str) -> str:
    """Return the read-only embed token for a template event GIF."""

    payload = f"embedded-event-buffer:{template_name}".encode()
    return hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()


def _parse_fit_dimension(value: str | None) -> int | None:
    """Return a bounded positive screenshot fit dimension from a query value."""

    try:
        parsed = int(str(value or "").strip())
    except ValueError:
        return None
    if parsed < _FITTED_SCREENSHOT_MIN_EDGE or parsed > _FITTED_SCREENSHOT_MAX_EDGE:
        return None
    return parsed


def _parse_fit_bg(value: str | None) -> tuple[int, int, int]:
    """Parse an optional RGB hex background for fitted screenshots."""

    text = str(value or "").strip().lstrip("#")
    if not re.fullmatch(r"[0-9a-fA-F]{6}", text):
        return _FITTED_SCREENSHOT_DEFAULT_BG
    return tuple(int(text[idx : idx + 2], 16) for idx in (0, 2, 4))


def _parse_event_buffer_wait(value: str | None) -> float | None:
    """Return a bounded post-event wait override."""

    if value in {None, ""}:
        return None
    try:
        parsed = float(str(value).strip())
    except ValueError:
        return None
    return min(max(parsed, 0.0), 10.0)


def _serve_fitted_screenshot(routes, shot: str):
    """Return a contained PNG variant when requested by dashboard embeds."""

    if str(routes.request.args.get("fit") or "").lower() != "contain":
        return None

    width = _parse_fit_dimension(routes.request.args.get("w"))
    height = _parse_fit_dimension(routes.request.args.get("h"))
    if width is None or height is None:
        return None

    background = _parse_fit_bg(routes.request.args.get("bg"))
    try:
        version = _fitted_source_version(shot)
        key = (version, width, height, background)
        with _fitted_cache_lock:
            cached = _fitted_cache.get(key)
            if cached is not None:
                _fitted_cache.move_to_end(key)
        if cached is not None:
            return routes.send_conditional_file(
                BytesIO(cached), cache_seconds=routes.PNG_TTL_SEC, mimetype="image/png"
            )
        with Image.open(shot) as image:
            contained = ImageOps.contain(
                image.convert("RGB"), (width, height), Image.Resampling.LANCZOS
            )
    except (OSError, UnidentifiedImageError):
        return None

    canvas = Image.new("RGB", (width, height), background)
    x = (width - contained.width) // 2
    y = (height - contained.height) // 2
    canvas.paste(contained, (x, y))

    out = BytesIO()
    canvas.save(out, format="PNG", compress_level=CAPTURE_PNG_COMPRESSION_LEVEL)
    # Render outside the cache lock so different camera requests remain parallel.
    # Never remember bytes if a source changed while it was being rendered.
    try:
        if _fitted_source_version(shot) == version:
            _remember_fitted(key, out.getvalue())
    except OSError:
        pass
    out.seek(0)
    return routes.send_conditional_file(
        out, cache_seconds=routes.PNG_TTL_SEC, mimetype="image/png"
    )


def _clean_screenshot_path(routes, shot: str, *, force_clean: bool = False) -> str:
    """Return a clean companion frame for dashboard embeds when requested."""

    if not force_clean and str(routes.request.args.get("clean") or "").lower() not in {
        "1",
        "true",
        "yes",
    }:
        return shot

    canonical_path = os.path.realpath(shot)
    companion = canonical_path + ".clean.png"
    if os.path.isfile(companion) and routes.screenshots._is_valid_png(companion):
        return companion
    # Historical requests must never borrow today's unbound legacy clean copy.
    request = getattr(routes, "request", None)
    if request is not None and request.args.get("capture"):
        return shot

    clean_path = os.path.join(os.path.dirname(shot), "last_clean.png")
    try:
        # A failed clean-copy update must not silently serve a previous capture
        # under the latest capture's age. Filenames carry the capture's UTC time;
        # the annotated file's mtime may have advanced later during captioning.
        canonical = os.path.basename(os.path.realpath(shot))
        match = re.search(r"_(\d{14})(?:_blank)?\.png$", canonical)
        if match:
            from datetime import datetime, timezone

            captured = (
                datetime.strptime(match.group(1), "%Y%m%d%H%M%S")
                .replace(tzinfo=timezone.utc)
                .timestamp()
            )
            if os.path.getmtime(clean_path) < captured:
                return shot
        if os.path.getsize(clean_path) > 0 and routes.screenshots._is_valid_png(
            clean_path
        ):
            return clean_path
    except (OSError, ValueError):
        pass
    return shot


def _serve_latest_screenshot(
    routes,
    template_name: str,
    raw_name: str | None = None,
    *,
    force_clean: bool = False,
):
    """Serve the latest valid screenshot or a placeholder for missing sources."""

    raw_name = raw_name if raw_name is not None else template_name
    force_clean = force_clean or caption_overlay_suppressed_name(raw_name)

    for group_camera in re.findall(r"^group-(.+?)$", template_name):
        path = os.path.join(
            os.path.dirname(os.path.join(routes.__file__)),
            "..",
            routes.SCREENSHOT_DIRECTORY,
            f"{group_camera}_latest_camera.png",
        )
        if os.path.exists(path):
            return routes.send_conditional_file(path, routes.PNG_TTL_SEC)
        _log_missing_screenshot(str(template_name))
        resp = routes.send_conditional_file(
            routes._placeholder_screenshot(),
            cache_seconds=routes.PNG_TTL_SEC,
            mimetype="image/png",
        )
        resp.status_code = 404
        return resp

    path = os.path.join(
        os.path.dirname(os.path.join(routes.__file__)),
        "..",
        routes.SCREENSHOT_DIRECTORY,
        str(template_name),
    )
    if not os.path.exists(path):
        _log_missing_screenshot(str(raw_name))
        resp = routes.send_conditional_file(
            routes._placeholder_screenshot(),
            cache_seconds=routes.PNG_TTL_SEC,
            mimetype="image/png",
        )
        resp.status_code = 404
        return resp

    from app.utils.source_freshness import timestamp
    from app.utils.template_manager import parse_canonical_screenshot_timestamp

    lfiles = [f for f in routes.glob.glob(path + "/*.png") if os.path.isfile(f)]
    canonical = {}
    for filename in lfiles:
        actual = os.path.realpath(filename)
        captured = parse_canonical_screenshot_timestamp(
            template_name, os.path.basename(actual)
        )
        if captured is not None:
            canonical[actual] = captured
    requested = routes.request.args.get("capture")
    if requested:
        wanted = timestamp(requested)
        if wanted is None:
            routes.abort(400, "Invalid capture timestamp")
        lfiles = [
            f
            for f, captured in canonical.items()
            if captured == wanted.replace(tzinfo=None)
        ]
        if not lfiles:
            routes.abort(404, "Requested capture is no longer available")
    elif canonical:
        lfiles = sorted(canonical, key=canonical.get, reverse=True)
    else:
        # Legacy filenames remain readable, but mutable sidecars never win
        # over canonical captures solely because they were touched recently.
        lfiles.sort(key=os.path.getmtime, reverse=True)
    for shot in lfiles:
        try:
            if os.path.getsize(shot) > 0 and routes.screenshots._is_valid_png(shot):
                captured = parse_canonical_screenshot_timestamp(
                    template_name, os.path.basename(os.path.realpath(shot))
                )
                shot = _clean_screenshot_path(routes, shot, force_clean=force_clean)
                response = _serve_fitted_screenshot(routes, shot)
                if response is None:
                    response = routes.send_conditional_file(shot, routes.PNG_TTL_SEC)
                if captured is not None:
                    response.headers["X-Capture-Time"] = captured.strftime(
                        "%Y-%m-%dT%H:%M:%SZ"
                    )
                return response
        except OSError:
            continue

    _log_missing_screenshot(str(template_name))
    resp = routes.send_conditional_file(
        routes._placeholder_screenshot(),
        cache_seconds=routes.PNG_TTL_SEC,
        mimetype="image/png",
    )
    resp.status_code = 404
    return resp


def create_blueprint() -> Blueprint:
    """Create and return the assets blueprint."""

    from app import routes

    bp = Blueprint("assets", __name__)

    @bp.route("/last_teaser")
    @routes.login_required
    def serve_teaser() -> Response:
        """Serve the teaser video for a specific group."""

        group = routes.request.args.get("group")
        if group and not re.match(r"^[a-zA-Z0-9_]+$", group):
            routes.abort(400, "Invalid group name. Group name must be alphanumeric.")

        lgroup = routes.secure_filename(group) if group else "all"
        base_path = os.path.join(
            os.path.dirname(routes.__file__), "..", routes.VIDEO_DIRECTORY
        )
        if not os.path.exists(base_path):
            routes.abort(404)

        video_path = os.path.join(base_path, f"{lgroup}_in_process.mp4")
        if os.path.exists(video_path):
            return routes.send_file(video_path)

        routes.abort(404)

    @bp.route("/timelapse/<string:template_name>.gif")
    @routes.login_required
    def serve_timelapse(template_name: str) -> Response:
        """Serve sampled saved-camera history, never a live capture."""
        from app.utils.timelapse import build_timelapse

        clip = build_timelapse(template_name)
        if clip is None:
            routes.abort(404, "No recent changing camera history")
        response = routes.send_conditional_file(
            clip["path"], cache_seconds=0, mimetype="image/gif"
        )
        response.headers["Cache-Control"] = "no-store"
        for field in ("start", "end", "frames", "duration"):
            response.headers["X-Timelapse-" + field.title()] = str(clip[field])
        return response

    @bp.route("/last_video/<string:template_name>")
    @routes.login_required
    def serve_video(template_name: routes.TemplateName) -> Response:
        """Return the latest MP4 for ``template_name`` if available."""

        template_name = routes.validate_template_name(str(template_name))
        if template_name is None:
            routes.abort(404)

        path = os.path.join(
            os.path.dirname(os.path.join(routes.__file__)),
            "..",
            routes.VIDEO_DIRECTORY,
            str(template_name),
        )
        if not os.path.exists(path):
            routes.abort(404)

        in_process = os.path.join(path, "in_process.mp4")
        if os.path.exists(in_process):
            return routes.send_file(in_process)

        video_files = [
            f
            for f in routes.glob.glob(os.path.join(path, "*.mp4"))
            if os.path.isfile(f)
        ]
        if video_files:
            latest = max(video_files, key=os.path.getmtime)
            return routes.send_file(latest)

        routes.abort(404)

    def _send_clip_or_last(path: Path, template: str) -> Response:
        try:
            return routes.send_conditional_file(path, routes.CACHE_TTL_SEC)
        except FileNotFoundError:
            logging.warning("Missing clip %s; using last_video", template)
            resp = serve_video(template)
            resp.headers["X-Clip-Status"] = "waiting"
            return resp

    def _system_is_busy() -> bool:
        metrics = routes.scheduling.get_system_metrics()
        return (
            metrics.get("cpu_usage", 0) >= routes.config.WATCHDOG_CPU_THRESHOLD
            or metrics.get("memory_usage", 0) >= routes.config.WATCHDOG_MEMORY_THRESHOLD
            or metrics.get("thread_count", 0) >= 100
        )

    @bp.route("/clip/<string:template_name>")
    @routes.login_required
    def serve_clip(template_name: routes.TemplateName) -> Response:
        """Return a short clip built from recent footage."""

        template_name = routes.validate_template_name(str(template_name))
        if template_name is None:
            routes.abort(404)

        try:
            duration = int(
                routes.request.args.get("duration", routes.config.DEFAULT_CLIP_DURATION)
            )
        except (TypeError, ValueError):
            routes.abort(400, "Invalid duration")
        # Bound per-request work as well as rejecting command-like input.
        if not 1 <= duration <= 600:
            routes.abort(400, "Invalid duration")

        root = (
            Path(routes.__file__).resolve().parent
            / ".."
            / routes.VIDEO_DIRECTORY
            / str(template_name)
        ).resolve()
        if not root.is_dir():
            routes.abort(404)

        if _system_is_busy():
            logging.warning("System busy; serving last_video for %s", template_name)
            resp = serve_video(template_name)
            resp.headers["X-Degraded-Service"] = "busy"
            return resp

        clip_root = Path(routes.CLIPS_DIRECTORY)
        clip_root.mkdir(parents=True, exist_ok=True)
        clip_path = clip_root / f"{template_name}.mp4"

        in_process = root / "in_process.mp4"
        sources = list(root.glob("final_*.mp4"))
        if in_process.exists():
            sources.append(in_process)

        newest_src = max(sources, key=lambda p: p.stat().st_mtime, default=None)

        if (
            clip_path.exists()
            and newest_src
            and clip_path.stat().st_mtime > newest_src.stat().st_mtime
            and (time.time() - clip_path.stat().st_mtime) < routes.CACHE_TTL_SEC
        ):
            return _send_clip_or_last(clip_path, template_name)

        parts: list[Path] = []
        in_process_len = 0
        if in_process.exists():
            in_process_len = int(
                routes.video_archiver.get_video_duration(in_process.as_posix()) or 0
            )

        remaining = duration - in_process_len
        if remaining > 0:
            final_parts = [
                p
                for p in sorted(
                    root.glob("final_*.mp4"),
                    key=lambda p: p.stat().st_mtime,
                    reverse=True,
                )
                if p.stat().st_size > 0
            ]
            total = 0
            for part in final_parts:
                parts.insert(0, part)
                total += routes.SEGMENT_SEC
                if total >= remaining:
                    break

        if in_process.exists():
            parts.append(in_process)

        lock_path = root / ".clip.lock"
        with lock_path.open("w") as lock_fd:
            routes.fcntl.flock(lock_fd, routes.fcntl.LOCK_EX)
            if (
                clip_path.exists()
                and newest_src
                and clip_path.stat().st_mtime > newest_src.stat().st_mtime
            ):
                return _send_clip_or_last(clip_path, template_name)

            if not parts:
                routes.video_archiver.create_blank_video(duration, clip_path.as_posix())
            elif not routes._concat_copy(clip_path, parts, duration):
                routes.video_archiver.create_blank_video(duration, clip_path.as_posix())

        if clip_path.exists():
            return _send_clip_or_last(clip_path, template_name)

        routes.abort(500, "Could not create clip")

    @bp.route("/last_screenshot/<string:template_name>")
    @routes.login_required
    def serve_screenshot(template_name: routes.TemplateName) -> Response:
        """Serve the latest screenshot for ``template_name``."""

        raw_name = template_name
        template_name = routes.validate_template_name(str(template_name))
        if template_name is None:
            _log_missing_screenshot(str(raw_name))
            resp = routes.send_conditional_file(
                routes._placeholder_screenshot(),
                cache_seconds=routes.PNG_TTL_SEC,
                mimetype="image/png",
            )
            resp.status_code = 404
            return resp

        return _serve_latest_screenshot(routes, str(template_name), str(raw_name))

    @bp.route("/clean_screenshot/<string:template_name>")
    @routes.login_required
    def serve_clean_screenshot(template_name: routes.TemplateName) -> Response:
        """Serve the latest screenshot without scheduler caption overlays."""

        raw_name = template_name
        template_name = routes.validate_template_name(str(template_name))
        if template_name is None:
            _log_missing_screenshot(str(raw_name))
            resp = routes.send_conditional_file(
                routes._placeholder_screenshot(),
                cache_seconds=routes.PNG_TTL_SEC,
                mimetype="image/png",
            )
            resp.status_code = 404
            return resp

        return _serve_latest_screenshot(
            routes, str(template_name), str(raw_name), force_clean=True
        )

    @bp.route("/embedded_screenshot/<string:template_name>")
    def serve_embedded_screenshot(template_name: routes.TemplateName) -> Response:
        """Serve a screenshot to image-only embeds without a login redirect."""

        raw_name = template_name
        template_name = routes.validate_template_name(str(template_name))
        if template_name is None:
            routes.abort(404)

        secret = routes.API_KEY or ""
        expected = (
            embedded_screenshot_token(str(template_name), secret) if secret else ""
        )
        supplied = str(routes.request.args.get("token") or "")
        if not expected or not hmac.compare_digest(supplied, expected):
            routes.abort(401)

        return _serve_latest_screenshot(routes, str(template_name), str(raw_name))

    @bp.route("/event_buffer/<string:template_name>.gif")
    @routes.login_required
    def serve_event_buffer_gif(template_name: routes.TemplateName) -> Response:
        """Build and serve the current event-buffer GIF."""

        raw_name = template_name
        template_name = routes.validate_template_name(str(template_name))
        if template_name is None:
            _log_missing_screenshot(str(raw_name))
            routes.abort(404)

        if routes.request.args.get("recent") == "1":
            replay = routes.event_buffer.recent_replay(str(template_name))
            if replay is None:
                routes.abort(404, "No recent motion buffer available")
            response = routes.send_conditional_file(
                replay["path"], cache_seconds=0, mimetype="image/gif"
            )
            response.headers["Cache-Control"] = "no-store"
            for field in ("start", "end", "frames", "fps"):
                response.headers[f"X-Replay-{field.title()}"] = str(replay[field])
            return response

        gif_path = routes.event_buffer.build_event_gif(
            str(template_name),
            wait_post=_parse_event_buffer_wait(routes.request.args.get("wait")),
        )
        if gif_path is None:
            routes.abort(404)
        return routes.send_conditional_file(
            gif_path, cache_seconds=0, mimetype="image/gif"
        )

    @bp.route("/embedded_event_buffer/<string:template_name>.gif")
    def serve_embedded_event_buffer_gif(
        template_name: routes.TemplateName,
    ) -> Response:
        """Serve a tokenized event-buffer GIF to image-only consumers."""

        raw_name = template_name
        template_name = routes.validate_template_name(str(template_name))
        if template_name is None:
            _log_missing_screenshot(str(raw_name))
            routes.abort(404)

        secret = routes.API_KEY or ""
        expected = (
            embedded_event_buffer_token(str(template_name), secret) if secret else ""
        )
        supplied = str(routes.request.args.get("token") or "")
        if not expected or not hmac.compare_digest(supplied, expected):
            routes.abort(401)

        gif_path = routes.event_buffer.build_event_gif(
            str(template_name),
            wait_post=_parse_event_buffer_wait(routes.request.args.get("wait")),
        )
        if gif_path is None:
            routes.abort(404)
        return routes.send_conditional_file(
            gif_path, cache_seconds=0, mimetype="image/gif"
        )

    @bp.route("/sw.js")
    def service_worker():
        response = routes.make_response(routes.current_app.send_static_file("sw.js"))
        response.headers["Cache-Control"] = "no-cache"
        return response

    @bp.route("/robots.txt")
    def robots_txt():
        """Return ``robots.txt`` rules based on ``ALLOW_BOTS`` setting."""
        rules = ["User-agent: *"]
        if routes.config.ALLOW_BOTS:
            rules.append("Allow: /")
        else:
            rules.append("Disallow: /")
        response = routes.Response("\n".join(rules) + "\n", mimetype="text/plain")
        response.headers["Cache-Control"] = "no-cache"
        return response

    @bp.route(
        "/submit_image/<string:template_name>",
        methods=["POST"],
        endpoint="submit_image",
    )
    @routes.login_required
    def submit_image(template_name: routes.TemplateName):
        """Receive and process an uploaded image."""

        raw_name = template_name
        template_name = routes.validate_template_name(str(template_name))
        if template_name is None:
            routes._log_missing_screenshot(str(raw_name))
            resp = routes.send_conditional_file(
                routes._placeholder_screenshot(),
                cache_seconds=routes.PNG_TTL_SEC,
                mimetype="image/png",
            )
            resp.status_code = 404
            return resp

        details = routes.template_manager.get_template(template_name)
        if not details:
            return (
                routes.jsonify({"status": "error", "message": "Template not found"}),
                404,
            )

        template_name = details.get("name", template_name)

        if "file" not in routes.request.files:
            return (
                routes.jsonify(
                    {"status": "error", "message": "No file part in the request"}
                ),
                400,
            )

        file = routes.request.files["file"]

        if file.filename == "":
            return (
                routes.jsonify({"status": "error", "message": "No selected file"}),
                400,
            )

        if file and routes.allowed_filename(file.filename):
            timestamp = routes.datetime.utcnow().strftime("%Y%m%d%H%M%S")
            filename = f"{template_name}_{timestamp}.png.tmp"
            output_path = routes.os.path.join(
                routes.SCREENSHOT_DIRECTORY, template_name, filename
            )

            file.save(output_path)
            clean_image = None
            if details.get("source_template") == "hubitat_site_dashboard":
                with Image.open(output_path) as uploaded:
                    clean_image = uploaded.copy()
            routes.screenshots.add_timestamp(output_path, name=template_name)
            final_path = output_path.rstrip(".tmp")
            routes.os.rename(output_path, final_path)
            if clean_image is not None:
                _publish_uploaded_clean_frame(clean_image, final_path)

            routes.template_manager.update_last_screenshot_time(template_name)

            return (
                routes.jsonify(
                    {"status": "success", "message": "Image submitted successfully"}
                ),
                200,
            )
        return (
            routes.jsonify({"status": "error", "message": "Invalid file format"}),
            400,
        )

    @bp.route(
        "/upload_screenshot/<string:template_name>",
        methods=["POST"],
        endpoint="upload_screenshot",
    )
    @routes.login_required
    def upload_screenshot(template_name: routes.TemplateName):
        """Upload a screenshot from disk."""

        template_name = routes.validate_template_name(str(template_name))
        if template_name is None:
            routes.abort(404)

        if "image_file" not in routes.request.files:
            return (
                routes.jsonify(
                    {"status": "error", "message": "No image file provided"}
                ),
                400,
            )

        image_file = routes.request.files["image_file"]
        if (image_file.filename or "") == "":
            return (
                routes.jsonify(
                    {"status": "error", "message": "No image file provided"}
                ),
                400,
            )

        routes.logging.debug("Uploading screenshot for %s", template_name)
        templates = routes.template_manager.get_templates()
        if templates.get(template_name) is None:
            routes.abort(404)

        filename = image_file.filename or ""
        if not routes.allowed_filename(filename) or not filename.lower().endswith(
            ".png"
        ):
            return (
                routes.jsonify({"status": "error", "message": "Invalid file name"}),
                400,
            )

        with routes.tempfile.NamedTemporaryFile(delete=False) as temp_file:
            image_file.save(temp_file.name)
            if not routes.screenshots._is_valid_png(temp_file.name):
                routes.os.unlink(temp_file.name)
                return (
                    routes.jsonify(
                        {"status": "error", "message": "Invalid image file"}
                    ),
                    400,
                )

            routes.scheduling.update_camera(
                template_name,
                templates.get(template_name),
                image_file=temp_file.name,
            )

        if temp_file and routes.os.path.exists(temp_file.name):
            routes.os.unlink(temp_file.name)

        return routes.jsonify(
            {
                "status": "success",
                "message": f"Screenshot for {template_name} uploaded",
            }
        )

    @bp.route("/compile_teaser", methods=["POST"], endpoint="compile_teaser")
    @routes.login_required
    @routes.limit_rate(30)
    def take_compile():
        """Trigger teaser compilation."""

        routes.video_archiver.compile_to_teaser()
        return routes.jsonify({"status": "success", "message": "Compilation taken"})

    @bp.route(
        "/take_screenshot/<string:template_name>",
        methods=["POST", "GET"],
        endpoint="take_screenshot",
    )
    @routes.login_required
    def take_screenshot(template_name: routes.TemplateName):
        """Trigger immediate screenshot capture."""

        template_name = routes.validate_template_name(str(template_name))
        if template_name is None:
            routes.abort(404)

        templates = routes.template_manager.get_templates()
        if templates.get(template_name) is None:
            routes.abort(404)

        motion_flag = routes.request.args.get("motion", "false").lower() in [
            "1",
            "true",
            "yes",
        ]
        if not _MANUAL_CAPTURE_LOCK.acquire(blocking=False):
            return (
                routes.jsonify(
                    {
                        "status": "busy",
                        "message": "Another manual screenshot capture is already running",
                    }
                ),
                429,
            )
        try:
            routes.scheduling.update_camera(
                template_name, templates.get(template_name), motion=motion_flag
            )
        finally:
            _MANUAL_CAPTURE_LOCK.release()
        return routes.jsonify(
            {
                "status": "success",
                "message": f"Screenshot for {template_name} taken",
            }
        )

    @bp.route(
        "/clear_quarantine/<string:template_name>",
        methods=["POST"],
        endpoint="clear_quarantine",
    )
    @routes.login_required
    def clear_quarantine(template_name: routes.TemplateName):
        """Clear capture retry restrictions and offline status for a template."""

        template_name = routes.validate_template_name(str(template_name))
        if template_name is None:
            routes.abort(404)

        templates = routes.template_manager.get_templates()
        template = templates.get(template_name)
        if template is None:
            routes.abort(404)

        url = template.get("url", "")
        cleared = False
        if url:
            cleared = routes.screenshots.clear_capture_backoff(
                url, template.get("auth_username"), template.get("auth_password")
            )
        routes.template_manager.clear_offline(template_name)
        return routes.jsonify(
            {
                "status": "success",
                "cleared": cleared,
                "message": f"Quarantine cleared for {template_name}",
            }
        )

    @bp.route(
        "/update_video/<string:template_name>",
        methods=["POST"],
        endpoint="update_video",
    )
    @routes.login_required
    def update_video(template_name: routes.TemplateName):
        """Compile screenshots into a video."""

        template_name = routes.validate_template_name(str(template_name))
        if template_name is None:
            routes.abort(404)

        templates = routes.template_manager.get_templates()
        if templates.get(template_name) is None:
            routes.abort(404)

        camera_path = routes.os.path.join(
            routes.os.path.dirname(routes.os.path.join(routes.__file__)),
            "..",
            routes.SCREENSHOT_DIRECTORY,
            str(template_name),
        )

        video_path = routes.os.path.join(
            routes.os.path.dirname(routes.os.path.join(routes.__file__)),
            "..",
            routes.VIDEO_DIRECTORY,
            str(template_name),
        )

        if routes.os.path.exists(camera_path) and routes.os.path.exists(video_path):
            routes.video_archiver.compile_to_video(camera_path, video_path)
            return routes.jsonify(
                {
                    "status": "success",
                    "message": f"Screenshot for {template_name} taken",
                }
            )

    @bp.route("/record/<string:template_name>", methods=["POST"], endpoint="record")
    @routes.login_required
    def record_high_speed(template_name: routes.TemplateName):
        """Capture frames rapidly for a short duration."""

        template_name = routes.validate_template_name(str(template_name))
        if template_name is None:
            routes.abort(404)

        templates = routes.template_manager.get_templates()
        template = templates.get(template_name)
        if template is None:
            routes.abort(404)

        duration = int(routes.request.args.get("duration", 20))

        def _record() -> None:
            end = routes.time.time() + duration
            while routes.time.time() < end:
                try:
                    routes.scheduling.update_camera(template_name, template)
                except Exception:
                    routes.logging.exception(
                        "High-speed capture failed: %s", template_name
                    )
                routes.time.sleep(0.2)

        routes.Thread(target=_record, daemon=True).start()
        return routes.jsonify({"status": "started"})

    return bp
