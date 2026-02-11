from __future__ import annotations

import logging
import os
import re
import time
from pathlib import Path

from flask import Blueprint, Response


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

        duration = (
            routes.request.args.get("duration", type=int)
            or routes.config.DEFAULT_CLIP_DURATION
        )
        if duration <= 0:
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
            logging.warning("Unable to serve screenshot for %s", raw_name)
            resp = routes.send_conditional_file(
                routes._placeholder_screenshot(),
                cache_seconds=routes.PNG_TTL_SEC,
                mimetype="image/png",
            )
            resp.status_code = 404
            return resp

        for group_camera in re.findall(r"^group-(.+?)$", template_name):
            path = os.path.join(
                os.path.dirname(os.path.join(routes.__file__)),
                "..",
                routes.SCREENSHOT_DIRECTORY,
                f"{group_camera}_latest_camera.png",
            )
            if os.path.exists(path):
                return routes.send_conditional_file(path, routes.PNG_TTL_SEC)
            logging.warning("Unable to serve screenshot for %s", template_name)
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
            logging.warning("Unable to serve screenshot for %s", template_name)
            resp = routes.send_conditional_file(
                routes._placeholder_screenshot(),
                cache_seconds=routes.PNG_TTL_SEC,
                mimetype="image/png",
            )
            resp.status_code = 404
            return resp

        lfiles = [f for f in routes.glob.glob(path + "/*.png") if os.path.isfile(f)]
        lfiles.sort(key=os.path.getmtime, reverse=True)
        for shot in lfiles:
            try:
                if os.path.getsize(shot) > 0 and routes.screenshots._is_valid_png(shot):
                    return routes.send_conditional_file(shot, routes.PNG_TTL_SEC)
            except OSError:
                continue

        logging.warning("Unable to serve screenshot for %s", template_name)
        resp = routes.send_conditional_file(
            routes._placeholder_screenshot(),
            cache_seconds=routes.PNG_TTL_SEC,
            mimetype="image/png",
        )
        resp.status_code = 404
        return resp

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
            routes.logging.warning("Unable to serve screenshot for %s", raw_name)
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
            routes.screenshots.add_timestamp(output_path, name=template_name)
            final_path = output_path.rstrip(".tmp")
            routes.os.rename(output_path, final_path)

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
        routes.scheduling.update_camera(
            template_name, templates.get(template_name), motion=motion_flag
        )
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
        """Clear local quarantine and offline status for a template."""

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
            cleared = routes.screenshots.clear_local_quarantine(url)
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
