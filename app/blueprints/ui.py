from __future__ import annotations

import hashlib
import io
import json
import logging
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

from flask import (
    Blueprint,
    Response,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)

_MISSING_SCREENSHOT_LOG_INTERVAL_SECONDS = 300
_missing_screenshot_log_ts: dict[str, float] = {}

# Tiny per-process cache for the templates JSON payload. The templates UI polls
# frequently; this keeps the endpoint responsive under load and enables ETag/304.
_TEMPLATES_JSON_CACHE: dict[tuple[str, str, str], dict[str, object]] = {}
_TEMPLATES_JSON_CACHE_TTL_SECONDS = 1.0


def _log_missing_screenshot(name: str) -> None:
    """Rate-limit noisy missing-screenshot warnings per source."""

    now = time.monotonic()
    key = (name or "unknown").strip() or "unknown"
    last = _missing_screenshot_log_ts.get(key, 0.0)
    if now - last >= _MISSING_SCREENSHOT_LOG_INTERVAL_SECONDS:
        _missing_screenshot_log_ts[key] = now
        logging.warning("Unable to serve screenshot for %s", key)


def create_blueprint() -> Blueprint:
    """Create and return the UI blueprint with web routes."""

    from app import routes
    from app.utils import recovery

    bp = Blueprint("ui", __name__)

    @bp.route("/danger", methods=["GET", "POST"], endpoint="danger_mode")
    @routes.login_required
    def danger_mode():
        """Display and configure danger mode settings."""

        if request.method == "POST":
            action = request.form.get("action")
            if action == "update_shortcut":
                path_val = request.form.get("shortcut_path")
                path = Path(path_val) if path_val else None
                paths, msg = routes.update_chrome_shortcuts_info(path)
                if paths:
                    joined = ", ".join(str(p) for p in paths)
                    routes.flash(
                        f"Updated {len(paths)} shortcut{'s' if len(paths) != 1 else ''}: {joined}",
                        "success",
                    )
                else:
                    routes.flash(f"Failed to update shortcuts: {msg}", "error")
            else:
                enabled = "enabled" in request.form
                routes.update_setting("DANGER_MODE", "True" if enabled else "False")
            return redirect(url_for("danger_mode"))

        current = routes.config.get_setting("DANGER_MODE", "True") == "True"
        templates = routes.template_manager.get_templates()
        danger_cameras = sorted(
            [name for name, t in templates.items() if t.get("danger")]
        )

        chrome_path = routes.get_chrome_path()
        shortcut_opts = [
            str(p) for p in routes.LINUX_PATHS if p.exists() and os.access(p, os.W_OK)
        ]
        danger_info = {
            "browser": os.path.basename(chrome_path) if chrome_path else "N/A",
            "path": chrome_path or "N/A",
            "version": routes.get_chrome_version(chrome_path) if chrome_path else "N/A",
            "shortcut": str(routes.first_shortcut_path() or "N/A"),
            "patched": not routes.shortcuts_need_patch(),
            "running": routes.is_chrome_debug_port_open(
                "127.0.0.1", routes.config.DANGER_PORT
            ),
            "port": routes.config.DANGER_PORT,
        }

        return render_template(
            "danger.html",
            enabled=current,
            danger_cameras=danger_cameras,
            danger_info=danger_info,
            shortcut_options=shortcut_opts,
            page_title="Danger Mode",
        )

    @bp.route("/stream", endpoint="stream")
    @routes.login_required
    def stream():
        """Render the main streaming page."""

        return render_template("stream.html", page_title="Stream")

    @bp.route("/groups", endpoint="get_groups")
    @routes.login_required
    def get_groups():
        """Return the list of active groups."""

        groups = routes.get_active_groups()
        if "all" not in groups:
            groups = ["all"] + groups
        return jsonify(groups)

    @bp.route("/captions", endpoint="captions")
    @routes.login_required
    def captions():
        """Display caption history and template details."""

        cost_start = request.args.get("cost_start")
        cost_end = request.args.get("cost_end")

        entries: list[dict[str, str]] = []
        latest_caption = ""
        try:
            session_db = routes.SessionLocal()
            try:
                records = (
                    session_db.query(routes.Summary)
                    .order_by(routes.Summary.timestamp.desc())
                    .limit(100)
                    .all()
                )
                for rec in records:
                    try:
                        data = json.loads(rec.content)
                        for ts, text in data.items():
                            try:
                                dt = datetime.utcfromtimestamp(int(ts))
                                iso_ts = dt.strftime("%Y-%m-%dT%H:%M:%SZ")
                            except (
                                ValueError,
                                OSError,
                                TypeError,
                                OverflowError,
                            ) as exc:
                                logging.warning("Invalid timestamp %s: %s", ts, exc)
                                iso_ts = ts
                            entries.append({iso_ts: text})
                    except Exception as exc:  # pragma: no cover - log parse issue
                        logging.error("Failed to parse captions: %s", exc)
            finally:
                session_db.close()
        except Exception as exc:  # pragma: no cover - db unavailable
            logging.error("Failed to query captions: %s", exc)
            entries = []

        if entries:
            try:
                latest_caption = next(iter(entries[0].values()))
            except Exception as exc:  # pragma: no cover - unexpected parse issue
                logging.error("Failed to obtain latest caption: %s", exc)
                latest_caption = ""

        templates = routes.template_manager.get_templates()
        for name, template in templates.items():
            last_screenshot_time = template.get("last_screenshot_time")
            frequency = int(template.get("frequency", 30))
            if last_screenshot_time:
                last_screenshot = datetime.strptime(
                    last_screenshot_time, "%Y-%m-%d %H:%M:%S"
                )
                next_screenshot = last_screenshot + timedelta(minutes=frequency)
                template["next_screenshot_time"] = next_screenshot.strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
            else:
                template["next_screenshot_time"] = None
            template["screenshot_count"] = routes.template_manager.get_screenshot_count(
                name
            )
            template["video_count"] = routes.template_manager.get_video_count(name)
            template["storage_usage"] = routes.template_manager.get_storage_usage(name)
            template["storage_usage_bytes"] = (
                routes.template_manager.get_storage_usage_bytes(name)
            )
            template["llm_response_count"] = (
                routes.template_manager.get_llm_response_count(name)
            )
            template["llm_cost_estimate"] = (
                routes.template_manager.get_llm_cost_estimate(
                    name, start_date=cost_start, end_date=cost_end
                )
            )

        return render_template(
            "captions.html",
            template_details=templates,
            lcaptions=entries,
            latest_caption=latest_caption,
            page_title="Captions",
            cost_start=cost_start,
            cost_end=cost_end,
        )

    @bp.route("/download_captions_tsv", endpoint="download_captions_tsv")
    @routes.login_required
    def download_captions_tsv() -> Response:
        """Return all template captions as a TSV file."""

        templates = routes.template_manager.get_templates()
        output = io.StringIO()
        writer = routes.csv.writer(output, delimiter="\t")
        writer.writerow(["name", "groups", "notes", "last_caption"])
        for name, template in templates.items():
            writer.writerow(
                [
                    name,
                    template.get("groups", ""),
                    template.get("notes", ""),
                    template.get("last_caption", ""),
                ]
            )
        output.seek(0)
        return Response(
            output.getvalue(),
            mimetype="text/tab-separated-values",
            headers={"Content-Disposition": "attachment;filename=captions.tsv"},
        )

    @bp.route("/upload_captions_tsv", methods=["POST"], endpoint="upload_captions_tsv")
    @routes.login_required
    def upload_captions_tsv():
        """Upload a TSV file and update template captions."""

        if "tsv_file" not in request.files:
            routes.flash("No file part", "error")
            return redirect(url_for("captions"))
        file = request.files["tsv_file"]
        if file.filename == "":
            routes.flash("No selected file", "error")
            return redirect(url_for("captions"))
        if file and file.filename.endswith(".tsv"):
            stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
            reader = routes.csv.reader(stream, delimiter="\t")
            next(reader, None)
            updated_count = 0
            for row in reader:
                if len(row) >= 4:
                    name, groups, notes, last_caption = row[:4]
                    template_name = routes.validate_template_name(name)
                    if template_name is None:
                        continue
                    template = routes.template_manager.get_template(template_name)
                    if template:
                        updates = {"groups": groups, "notes": notes}
                        if last_caption and last_caption != template.get(
                            "last_caption", ""
                        ):
                            updates["last_caption"] = last_caption
                            updates["last_caption_time"] = datetime.utcnow().strftime(
                                "%Y-%m-%d %H:%M:%S"
                            )
                        if routes.template_manager.save_template(
                            template_name, updates
                        ):
                            updated_count += 1
            routes.flash(f"Successfully updated {updated_count} templates", "success")
            return redirect(url_for("captions"))
        routes.flash("Invalid file format. Please upload a TSV file.", "error")
        return redirect(url_for("captions"))

    @bp.route("/captions_chat", methods=["POST"], endpoint="captions_chat")
    @routes.login_required
    def captions_chat():
        """Answer a user question using recent caption history."""

        data = request.get_json(force=True) or {}
        question = (data.get("question") or "").strip()
        if not question:
            return jsonify({"error": "Missing question"}), 400
        start = data.get("start")
        end = data.get("end")
        session_db = routes.SessionLocal()
        try:
            query = session_db.query(routes.Summary)
            if start:
                try:
                    start_ts = int(datetime.fromisoformat(start).timestamp())
                    query = query.filter(routes.Summary.timestamp >= start_ts)
                except (ValueError, TypeError) as exc:
                    logging.warning("Invalid start parameter %s: %s", start, exc)
            if end:
                try:
                    end_ts = int(datetime.fromisoformat(end).timestamp())
                    query = query.filter(routes.Summary.timestamp <= end_ts)
                except (ValueError, TypeError) as exc:
                    logging.warning("Invalid end parameter %s: %s", end, exc)
            records = query.limit(101).all()
            truncated = len(records) > 100
            records = records[:100]
            captions = []
            for rec in reversed(records):
                try:
                    jdata = json.loads(rec.content)
                    captions.extend(jdata.values())
                except json.JSONDecodeError as exc:
                    logging.error("Invalid summary JSON for %s: %s", rec.timestamp, exc)
                    captions.append(rec.content)
        finally:
            session_db.close()

        history = "\n".join(captions)
        answer = routes.ask_question(question, history) or ""

        ts = int(datetime.utcnow().timestamp())
        session_db = routes.SessionLocal()
        try:
            session_db.add(
                routes.Summary(timestamp=ts, content=json.dumps({ts: f"Q: {question}"}))
            )
            if answer:
                ts2 = ts + 1
                session_db.add(
                    routes.Summary(
                        timestamp=ts2, content=json.dumps({ts2: f"A: {answer}"})
                    )
                )
            session_db.commit()
        finally:
            session_db.close()

        return jsonify({"answer": answer, "truncated": truncated})

    @bp.route("/live", endpoint="live")
    @routes.login_required
    def live():
        """Render the live view page."""

        camera = request.args.get("camera")
        group = request.args.get("group")
        selected_camera = None
        selected_group = None
        if camera:
            camera = routes.validate_template_name(camera)
            if camera is None:
                routes.abort(400, "Invalid camera name")
            details = routes.template_manager.get_template(camera)
            if not details:
                routes.abort(404)
            templates = {camera: details}
            selected_camera = camera
        else:
            templates = routes.template_manager.get_templates()
            if group and group != "all":
                selected_group = group
                templates = {
                    name: template
                    for name, template in templates.items()
                    if group
                    in [g.strip() for g in str(template.get("groups", "")).split(",")]
                }
        # Add capability hints for smarter live playback decisions in the UI.
        templates = {
            name: {
                **(template or {}),
                "capabilities": routes.live_capabilities_for_template(
                    template or {},
                    probe_http=bool(selected_camera and name == selected_camera),
                ),
            }
            for name, template in (templates or {}).items()
        }

        return render_template(
            "live.html",
            template_details=templates,
            selected_camera=selected_camera,
            selected_group=selected_group,
            page_title="Live View",
        )

    @bp.route("/clock", endpoint="clock_page")
    @routes.login_required
    def clock_page():
        """Render a standalone clock page."""

        return render_template("clock.html", page_title="Clock")

    @bp.route("/latest_frame/<string:template_name>", endpoint="latest_frame")
    @routes.login_required
    def latest_frame(template_name: routes.TemplateName):
        """Serve the latest frame image for ``template_name``."""

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
        path = os.path.join(
            os.path.dirname(os.path.join(__file__)),
            "..",
            routes.SCREENSHOT_DIRECTORY,
            str(template_name),
        )
        if not os.path.exists(path):
            routes.abort(404)
        latest_file = max(
            (f for f in os.listdir(path) if f.endswith(".png")),
            key=lambda f: os.path.getmtime(os.path.join(path, f)),
        )
        if latest_file:
            return routes.send_conditional_file(
                os.path.join(path, latest_file), routes.PNG_TTL_SEC
            )
        routes.abort(404)

    @bp.route("/upload_nav_icon", methods=["POST"], endpoint="upload_nav_icon")
    @routes.login_required
    def upload_nav_icon():
        """Upload or choose a navigation icon."""

        choice = request.form.get("logo_choice")
        if choice in {"img/glimpser_small.png", "img/glimpser.png"}:
            routes.update_setting("NAV_ICON", choice)
            routes.flash("Navigation logo updated", "success")
            return redirect(url_for("ui.settings"))
        if "logo_file" not in request.files:
            routes.flash("No logo file provided", "error")
            return redirect(url_for("ui.settings")), 400
        logo_file = request.files["logo_file"]
        if logo_file.filename == "":
            routes.flash("No logo file provided", "error")
            return redirect(url_for("ui.settings")), 400
        if not routes.allowed_filename(
            logo_file.filename
        ) or not logo_file.filename.lower().endswith(".png"):
            routes.flash("Invalid file name", "error")
            return redirect(url_for("ui.settings")), 400
        with routes.tempfile.NamedTemporaryFile(delete=False) as temp_file:
            logo_file.save(temp_file.name)
            try:
                with routes.Image.open(temp_file.name) as img:
                    w, h = img.size
                if h == 0 or not 2 <= w / h <= 10:
                    os.unlink(temp_file.name)
                    routes.flash("Invalid aspect ratio", "error")
                    return redirect(url_for("ui.settings")), 400
            except (OSError, ValueError) as exc:
                os.unlink(temp_file.name)
                logging.error("Failed to process uploaded logo: %s", exc)
                routes.flash("Invalid image file", "error")
                return redirect(url_for("ui.settings")), 400
            static_root = routes.current_app.static_folder
            dest_dir = os.path.join(static_root, "img")
            # Tests run in parallel and use a shared `test_static/` path; a
            # different worker may delete the directory between steps.
            for _ in range(3):
                try:
                    os.makedirs(static_root, exist_ok=True)
                    os.makedirs(dest_dir, exist_ok=True)
                    break
                except FileNotFoundError:
                    continue
            dest_name = routes.secure_filename(logo_file.filename)
            dest_path = os.path.join(dest_dir, dest_name)
            routes.shutil.move(temp_file.name, dest_path)
            routes.update_setting("NAV_ICON", f"img/{dest_name}")
        routes.flash("Navigation logo uploaded", "success")
        return redirect(url_for("ui.settings"))

    @bp.route(
        "/templates", methods=["GET", "POST", "DELETE"], endpoint="manage_templates"
    )
    @routes.login_required
    def manage_templates():
        """Manage template metadata via CRUD operations."""

        if request.method == "POST":
            data = request.get_json(silent=True) or {}
            template_name = routes.validate_template_name(str(data.get("name", "")))
            if template_name is None:
                routes.abort(404)
            url = data.get("url", "")
            # If credentials were provided in the URL, move them into the
            # template auth fields (so we don't persist passwords in URLs).
            parsed = urlparse(url or "")
            if parsed.username and not data.get("auth_username"):
                data["auth_username"] = parsed.username
            if parsed.password and not data.get("auth_password"):
                data["auth_password"] = parsed.password
            if parsed.username or parsed.password:
                host = parsed.hostname or ""
                netloc = host
                if parsed.port:
                    netloc = f"{host}:{parsed.port}"
                url = parsed._replace(netloc=netloc).geturl()
                data["url"] = url

            if url and ("onvif" in url or urlparse(url).path in {"", "/"}):
                try:
                    endpoints = routes.camera_discovery.autodetect_onvif_endpoints(
                        url,
                        username=data.get("auth_username") or None,
                        password=data.get("auth_password") or None,
                    )
                    if endpoints.get("snapshot"):
                        data["url"] = endpoints["snapshot"]
                    elif endpoints.get("stream"):
                        data["url"] = endpoints["stream"]
                except Exception as exc:  # pragma: no cover - network issues
                    logging.error("ONVIF autodetect failed for %s: %s", url, exc)
            if routes.template_manager.save_template(template_name, data):
                return jsonify({"status": "success", "message": "Template saved"})
        elif request.method == "GET":
            group = request.args.get("group") or "all"
            search_query = request.args.get("search", "").lower()

            # Cache/ETag: keep the templates UI snappy (it polls often).
            session_user = session.get("user_id")
            user_id = (
                str(session_user)
                if session_user is not None
                else (request.remote_addr or "anon")
            )
            cache_key = (user_id, group, search_query)
            now = time.time()
            entry = _TEMPLATES_JSON_CACHE.get(cache_key)
            if (
                entry
                and now - float(entry.get("ts", 0.0) or 0.0)
                <= _TEMPLATES_JSON_CACHE_TTL_SECONDS
            ):
                etag = str(entry.get("etag") or "")
                body = entry.get("body") or b"{}"
                inm = request.headers.get("If-None-Match")
                if inm and etag and inm == etag:
                    resp = Response(status=304)
                    resp.headers["ETag"] = etag
                    resp.headers["Cache-Control"] = (
                        "private, max-age=0, must-revalidate"
                    )
                    return resp
                resp = Response(body, mimetype="application/json")
                resp.headers["ETag"] = etag
                resp.headers["Cache-Control"] = "private, max-age=0, must-revalidate"
                return resp

            templates = routes.template_manager.get_templates()
            filtered_templates: dict[str, dict[str, str]] = {}
            for name, template in templates.items():
                template_groups = template.get("groups", "").split(",")
                if (group == "all" or group in template_groups) and (
                    not search_query
                    or search_query in name.lower()
                    or search_query in template.get("url", "").lower()
                    or any(search_query in g.lower() for g in template_groups)
                ):
                    filtered_templates[name] = template

            # Stable JSON for deterministic ETags.
            body = json.dumps(
                filtered_templates, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
            etag = '"' + hashlib.sha1(body).hexdigest() + '"'
            _TEMPLATES_JSON_CACHE[cache_key] = {"ts": now, "etag": etag, "body": body}

            inm = request.headers.get("If-None-Match")
            if inm and inm == etag:
                resp = Response(status=304)
                resp.headers["ETag"] = etag
                resp.headers["Cache-Control"] = "private, max-age=0, must-revalidate"
                return resp

            resp = Response(body, mimetype="application/json")
            resp.headers["ETag"] = etag
            resp.headers["Cache-Control"] = "private, max-age=0, must-revalidate"
            return resp
        elif request.method == "DELETE":
            data = request.get_json(silent=True) or {}
            template_name = routes.validate_template_name(str(data.get("name", "")))
            if template_name is None:
                routes.abort(404)
            if routes.template_manager.delete_template(template_name):
                return jsonify({"status": "success", "message": "Template deleted"})
            return jsonify({"status": "failure", "message": "Template not found"}), 404
        return jsonify({"status": "failure"}), 400

    @bp.route("/templates/<string:template_name>", endpoint="template_details")
    @routes.login_required
    def template_details(template_name: routes.TemplateName):
        """Render a page showing details for ``template_name``."""

        template_name = routes.validate_template_name(str(template_name))
        if template_name is None:
            routes.abort(404)
        templates = routes.template_manager.get_templates()
        template_details = templates.get(template_name)
        if template_details is None:
            routes.abort(404)
        quarantine_active = False
        quarantine_remaining = 0
        quarantine_reason = None
        template_url = template_details.get("url", "")
        if template_url:
            (
                quarantine_active,
                quarantine_remaining,
                quarantine_reason,
            ) = routes.screenshots.local_quarantine_status(template_url)
        lscreenshots = routes.template_manager.get_screenshots_for_template(
            template_name
        )
        lvideos = routes.template_manager.get_videos_for_template(template_name)
        object_tokens = ["person", "car", "dog", "cat", "truck", "bus", "bicycle"]
        return render_template(
            "template_details.html",
            template_name=template_name,
            template_details=template_details,
            quarantine_active=quarantine_active,
            quarantine_remaining=quarantine_remaining,
            quarantine_reason=quarantine_reason,
            screenshots=lscreenshots,
            videos=lvideos,
            object_tokens=object_tokens,
            clip_model=routes.CLIP_MODEL_NAME,
            clip_gpu=routes.clip_gpu_available(),
            page_title="Camera Details",
        )

    @bp.route(
        "/recovery/search/<string:template_name>",
        methods=["POST"],
        endpoint="recovery_search",
    )
    @routes.login_required
    def recovery_search(template_name: routes.TemplateName):
        template_name = routes.validate_template_name(str(template_name))
        if template_name is None:
            routes.abort(404)
        template = routes.template_manager.get_template(template_name)
        if not template:
            routes.abort(404)
        data = request.get_json(force=True) or {}
        description = str(data.get("description") or "")
        exclude_urls = data.get("exclude_urls") or []
        try:
            candidates, prompt = recovery.search_alternatives(
                {"name": template_name, **template},
                description,
                exclude_urls=exclude_urls,
            )
        except Exception as exc:
            logging.warning("Recovery search failed for %s: %s", template_name, exc)
            return jsonify({"error": "recovery_search_failed"}), 502
        logging.info(
            "Recovery search for %s returned %d candidates",
            template_name,
            len(candidates),
        )
        return jsonify({"candidates": candidates, "prompt": prompt})

    @bp.route("/recovery/preview", methods=["POST"], endpoint="recovery_preview")
    @routes.login_required
    def recovery_preview():
        data = request.get_json(force=True) or {}
        url = str(data.get("url") or "")
        template_name = str(data.get("template_name") or "")
        if not url or not template_name:
            return jsonify({"error": "missing_fields"}), 400
        if routes.validate_template_name(template_name) is None:
            return jsonify({"error": "invalid_template"}), 400
        path, preview_type, error = recovery.generate_preview(url, template_name)
        if not path:
            return jsonify({"ok": False, "error": error or "preview_failed"}), 400
        filename = Path(path).name
        preview_url = url_for("ui.recovery_preview_file", filename=filename)
        return jsonify(
            {"ok": True, "preview_url": preview_url, "preview_type": preview_type}
        )

    @bp.route(
        "/recovery/preview/<string:filename>",
        methods=["GET"],
        endpoint="recovery_preview_file",
    )
    @routes.login_required
    def recovery_preview_file(filename: str):
        safe_name = Path(filename).name
        path = recovery.RECOVERY_DIR / safe_name
        if not path.exists():
            routes.abort(404)
        mimetype = "image/png" if path.suffix == ".png" else "video/mp4"
        return send_file(path, mimetype=mimetype, max_age=0)

    @bp.route(
        "/recovery/apply/<string:template_name>",
        methods=["POST"],
        endpoint="recovery_apply",
    )
    @routes.login_required
    def recovery_apply(template_name: routes.TemplateName):
        template_name = routes.validate_template_name(str(template_name))
        if template_name is None:
            routes.abort(404)
        data = request.get_json(force=True) or {}
        url = str(data.get("url") or "").strip()
        url = recovery.validate_recovery_url(url)
        if not url:
            return jsonify({"error": "invalid_url"}), 400
        routes.template_manager.save_template(template_name, {"url": url})
        template = routes.template_manager.get_template(template_name) or {}
        try:
            routes.scheduling.scheduler.remove_job(template_name)
        except LookupError as exc:
            logging.warning("Job removal failed for %s: %s", template_name, exc)
        routes.screenshots.create_blank_frame(template_name)
        try:
            seconds = int(template.get("frequency", 30 * 60))
            routes.scheduling.scheduler.add_job(
                func=routes.scheduling.update_camera,
                trigger="interval",
                seconds=seconds,
                args=[template_name, template],
                id=template_name,
                replace_existing=True,
            )
        except Exception as exc:  # pragma: no cover - scheduler failure
            logging.error("job schedule error: %s", exc)
        logging.info("Recovery applied for %s -> %s", template_name, url)
        return jsonify({"ok": True})

    @bp.route(
        "/generate_prompt/<string:template_name>",
        methods=["POST"],
        endpoint="generate_prompt_route",
    )
    @routes.login_required
    def generate_prompt_route(template_name: routes.TemplateName):
        """Return a suggested caption prompt for ``template_name``."""

        template_name = routes.validate_template_name(str(template_name))
        if template_name is None:
            routes.abort(404)
        prompt = routes.prompt_optimizer.generate_prompt(template_name)
        return jsonify({"prompt": prompt})

    @bp.route(
        "/suggest_fix/<string:template_name>",
        methods=["POST"],
        endpoint="suggest_fix_route",
    )
    @routes.login_required
    def suggest_fix_route(template_name: routes.TemplateName):
        """Return diagnostic info and replacement URL suggestions."""

        template_name = routes.validate_template_name(str(template_name))
        if template_name is None:
            routes.abort(404)
        details = routes.template_manager.get_template(template_name)
        if not details:
            routes.abort(404)
        url = details.get("url", "")
        xpaths = [details.get("popup_xpath", ""), details.get("dedicated_xpath", "")]
        info = routes.camera_fix.check_camera_template(url, xpaths)
        return jsonify(info)

    @bp.route(
        "/camera_diagnostics/<string:template_name>", endpoint="camera_diagnostics"
    )
    @routes.login_required
    def camera_diagnostics(template_name: routes.TemplateName) -> Response:
        """Return live diagnostics for ``template_name``."""

        template_name = routes.validate_template_name(str(template_name))
        if template_name is None:
            routes.abort(404)
        details = routes.template_manager.get_template(template_name)
        if not details:
            routes.abort(404)
        url = details.get("url", "")
        host = urlparse(url).hostname or url
        try:
            ip = routes.socket.gethostbyname(host)
        except routes.socket.gaierror as exc:
            logging.warning("Hostname resolution failed for %s: %s", host, exc)
            ip = host
        data: dict[str, routes.typing.Any] = {"ip": ip}
        latency = routes.camera_discovery._ping_latency(ip)
        if latency is not None:
            data["ping_ms"] = latency
        ports = routes.camera_discovery._detect_open_ports(
            ip, routes.camera_discovery.COMMON_PORTS
        )
        if ports:
            data["open_ports"] = ports
            for p in ports:
                if p in (80, 8080, 443):
                    banner = routes.camera_discovery._fetch_http_banner(ip, p)
                    for k, v in banner.items():
                        data.setdefault(k, v)
        dtype = routes.camera_discovery._classify_device(
            {
                "ip": ip,
                "protocol": details.get("protocol", urlparse(url).scheme or "http"),
                "port": details.get("port", urlparse(url).port or 0),
                "info": data,
            }
        )
        if dtype:
            data["device_type"] = dtype
        return jsonify(data)

    def delete_setting(name: str) -> bool:
        """Remove ``name`` from the settings table."""

        name = name.replace("'", "")[:32]
        if not routes.re.findall(r"^[A-Z_]+?$", name):
            return False
        session = routes.SessionLocal()
        try:
            session.execute(
                routes.text("DELETE FROM settings WHERE name = :name"), {"name": name}
            )
            session.commit()
        finally:
            session.close()
        return True

    @bp.route("/settings", methods=["GET", "POST"], endpoint="settings")
    @routes.login_required
    def settings():
        """Render and update configuration settings."""

        if request.method == "POST":
            email_settings = [
                "EMAIL_ENABLED",
                "EMAIL_SENDER",
                "EMAIL_RECIPIENTS",
                "EMAIL_SMTP_SERVER",
                "EMAIL_SMTP_PORT",
                "EMAIL_USE_TLS",
                "EMAIL_USERNAME",
                "EMAIL_PASSWORD",
            ]
            action = request.form.get("action")
            if action == "add":
                new_name = (request.form.get("new_name") or "").strip()
                new_value = (request.form.get("new_value") or "").strip()
                if not new_name or not new_value:
                    routes.flash("Setting name and value are required", "error")
                    return redirect(url_for("ui.settings")), 400
                if not routes.re.fullmatch(r"[A-Z_]+", new_name):
                    routes.flash(
                        "Setting names must contain only uppercase letters and underscores",
                        "error",
                    )
                    return redirect(url_for("ui.settings")), 400
                sanitized = routes.validate_setting(new_name, new_value)
                if sanitized is None:
                    routes.flash(f"Invalid value for {new_name}", "error")
                    return redirect(url_for("ui.settings")), 400
                routes.update_setting(new_name, sanitized)
            elif action == "delete":
                name_to_delete = request.form.get("name_to_delete")
                if name_to_delete:
                    delete_setting(name_to_delete)
            elif action == "update_email":
                for setting in email_settings:
                    value = request.form.get(setting)
                    if value is not None:
                        sanitized = routes.validate_setting(setting, value)
                        if sanitized is None:
                            routes.flash(f"Invalid value for {setting}", "error")
                            return redirect(url_for("ui.settings")), 400
                        routes.update_setting(setting, sanitized)
            elif action == "backup":
                if routes.backup_config():
                    routes.flash("Configuration backed up successfully", "success")
                else:
                    routes.flash("Failed to backup configuration", "error")
            elif action == "download":

                def generate() -> routes.typing.Generator[bytes, None, None]:
                    """Stream the configuration JSON after triggering a backup."""

                    yield b""
                    routes.backup_config()
                    if os.path.exists(routes.BACKUP_PATH):
                        with open(routes.BACKUP_PATH, "rb") as f:
                            for chunk in iter(lambda: f.read(8192), b""):
                                yield chunk

                headers = {
                    "Content-Disposition": "attachment; filename=config_backup.json"
                }
                return Response(
                    routes.stream_with_context(generate()),
                    mimetype="application/json",
                    headers=headers,
                )
            elif action == "upload":
                if "file" not in request.files:
                    routes.flash("No file part", "error")
                else:
                    file = request.files["file"]
                    if file.filename == "":
                        routes.flash("No selected file", "error")
                    elif file and allowed_file(file.filename):
                        file.stream.seek(0, os.SEEK_END)
                        size = file.stream.tell()
                        file.stream.seek(0)
                        if size > routes.MAX_UPLOAD_SIZE:
                            routes.flash("File exceeds 5 MB limit", "error")
                        else:
                            file.save(routes.BACKUP_PATH)
                            routes.restore_config()
                            routes.flash(
                                "Configuration restored successfully", "success"
                            )
                    else:
                        routes.flash("Invalid file type", "error")
            elif action == "test_email":
                routes.send_email_alert(
                    "Glimpser Test Email", "This is a test email from Glimpser."
                )
                routes.flash("Email test triggered. Check logs for results.", "info")
            elif action == "test_sms":
                routes.send_sms_alert("Test SMS from Glimpser")
                routes.flash("SMS test triggered. Check logs for results.", "info")
            elif action == "update_shortcut":
                path_val = request.form.get("shortcut_path")
                path = Path(path_val) if path_val else None
                paths, msg = routes.update_chrome_shortcuts_info(path)
                if paths:
                    joined = ", ".join(str(p) for p in paths)
                    routes.flash(
                        f"Updated {len(paths)} shortcut{'s' if len(paths) != 1 else ''}: {joined}",
                        "success",
                    )
                else:
                    routes.flash(f"Failed to update shortcuts: {msg}", "error")
            else:
                current = {s["name"]: s["value"] for s in routes.get_all_settings()}
                bool_settings = {
                    n for n, v in current.items() if routes.validators.is_bool_string(v)
                }
                for name in bool_settings:
                    if name in email_settings:
                        continue
                    new_val = (
                        "True"
                        if str(request.form.get(name, "")).lower()
                        in {"true", "on", "1", "t", "y", "yes"}
                        else "False"
                    )
                    routes.update_setting(name, new_val)
                for name, value in request.form.items():
                    if (
                        name in {"action", "new_name", "new_value", "name_to_delete"}
                        or name in email_settings
                        or name in bool_settings
                    ):
                        continue
                    sanitized = routes.validate_setting(name, value)
                    if sanitized is None:
                        routes.flash(f"Invalid value for {name}", "error")
                        continue
                    if name in routes.SETTINGS_CHOICES:
                        routes.update_setting(name, sanitized)
                        continue
                    routes.update_setting(name, sanitized)
            routes.flash("Settings updated successfully", "success")
            return redirect(url_for("ui.settings"))

        settings = routes.get_all_settings()
        settings_map = {s["name"]: str(s["value"]) for s in settings}
        grouped_settings: dict[str, list[dict[str, str]]] = {
            group: [] for group in routes.SETTINGS_GROUPS
        }
        grouped_settings["Other"] = []
        for setting in settings:
            placed = False
            for group, names in routes.SETTINGS_GROUPS.items():
                if setting["name"] in names:
                    grouped_settings[group].append(setting)
                    placed = True
                    break
            if not placed:
                grouped_settings["Other"].append(setting)
        if "Advanced" in grouped_settings:
            grouped_settings["Advanced"].extend(grouped_settings.get("Other", []))
        else:
            grouped_settings["Advanced"] = grouped_settings.get("Other", [])
        grouped_settings.pop("Other", None)
        grouped_settings = {g: items for g, items in grouped_settings.items() if items}
        collapsed_groups = {"Capture", "Admin", "Advanced"}
        file_location_items = [
            s for s in settings if s["name"] in routes.FILE_LOCATION_NAMES
        ]
        file_info = routes.file_location_metrics(file_location_items)
        metrics = routes.scheduling.get_system_metrics()
        feeds = routes.scheduling.get_feed_status()
        last_summary = routes.scheduling.get_last_summary_time()
        log_summary = routes.scheduling.get_or_generate_log_summary()
        top_failures = routes.scheduling.get_top_failures()
        scheduler_health = routes.scheduling.get_scheduler_health()
        danger_enabled = routes.config.get_setting("DANGER_MODE", "True") == "True"
        cost_summary, total_tokens, total_cost, total_calls = (
            routes.template_manager.get_llm_cost_summary()
        )
        cost_summary = routes.template_manager.group_cost_summary(cost_summary, top=10)
        chrome_path = routes.get_chrome_path()
        shortcut_opts = [
            str(p) for p in routes.LINUX_PATHS if p.exists() and os.access(p, os.W_OK)
        ]
        danger_info = {
            "browser": os.path.basename(chrome_path) if chrome_path else "N/A",
            "path": chrome_path or "N/A",
            "version": routes.get_chrome_version(chrome_path) if chrome_path else "N/A",
            "shortcut": str(routes.first_shortcut_path() or "N/A"),
            "patched": not routes.shortcuts_need_patch(),
            "running": routes.is_chrome_debug_port_open(
                "127.0.0.1", routes.config.DANGER_PORT
            ),
            "port": routes.config.DANGER_PORT,
        }
        last_backup = None
        if os.path.exists(routes.BACKUP_PATH):
            ts = datetime.fromtimestamp(os.path.getmtime(routes.BACKUP_PATH))
            last_backup = ts.strftime("%Y-%m-%d %H:%M:%S")
        templates = routes.template_manager.get_templates()
        existing_urls = {t.get("url"): n for n, t in templates.items() if t.get("url")}
        tooltips = dict(routes.SETTINGS_TOOLTIPS)
        if not metrics.get("ffmpeg_gpu_support"):
            tooltips["FFMPEG_HWACCEL"] = "Hardware acceleration not available"

        # Display runtime-effective values when low CPU mode clamps settings.
        effective_settings: dict[str, str] = {}
        if routes.config.LOW_CPU_MODE:
            computed = {
                "MAX_WORKERS": str(routes.config.MAX_WORKERS),
                "FFMPEG_THREADS": str(routes.config.FFMPEG_THREADS),
                "LIVE_FALLBACK_FPS": str(routes.config.LIVE_FALLBACK_FPS),
                "ARCHIVE_INTERVAL_MINUTES": str(
                    max(int(routes.config.ARCHIVE_INTERVAL_MINUTES), 5)
                ),
            }
            for name, value in computed.items():
                if settings_map.get(name) != value:
                    effective_settings[name] = value
        return render_template(
            "settings.html",
            grouped_settings=grouped_settings,
            collapsed_groups=collapsed_groups,
            tooltips=tooltips,
            metrics=metrics,
            feeds=feeds,
            last_summary=last_summary,
            log_summary=log_summary,
            top_failures=top_failures,
            scheduler_health=scheduler_health,
            cost_summary=cost_summary,
            total_tokens=total_tokens,
            total_cost=total_cost,
            total_calls=total_calls,
            danger_info=danger_info,
            shortcut_options=shortcut_opts,
            choices=routes.SETTINGS_CHOICES,
            boolean_fields=routes.validators.BOOLEAN_SETTINGS,
            danger_enabled=danger_enabled,
            numeric_fields=routes.NUMERIC_FIELDS,
            email_fields=routes.EMAIL_FIELDS,
            locked_settings=routes.LOCKED_SETTINGS,
            file_info=file_info,
            existing_urls=existing_urls,
            placeholders=routes.SETTINGS_PLACEHOLDERS,
            effective_settings=effective_settings,
            last_backup=last_backup,
            page_title="Settings",
        )

    def allowed_file(filename: str) -> bool:
        """Return True when ``filename`` is a JSON file."""

        return "." in filename and filename.rsplit(".", 1)[1].lower() == "json"

    @bp.route(
        "/update_template/<string:template_name>",
        methods=["POST"],
        endpoint="update_template",
    )
    @routes.login_required
    def update_template(template_name: routes.TemplateName):
        """Update metadata for ``template_name``."""

        template_name = routes.validate_template_name(str(template_name))
        if template_name is None:
            routes.abort(404)
        updated_data = {
            "url": request.form.get("url"),
            "frequency": request.form.get("frequency"),
            "timeout": request.form.get("timeout"),
            "notes": request.form.get("notes"),
            "popup_xpath": request.form.get("popup_xpath"),
            "dedicated_xpath": request.form.get("dedicated_xpath"),
            "callback_url": request.form.get("callback_url"),
            "proxy": request.form.get("proxy"),
            "auth_username": request.form.get("auth_username"),
            "auth_password": request.form.get("auth_password"),
            "rollback_frames": request.form.get("rollback_frames"),
            "groups": request.form.get("groups"),
            "object_filter": request.form.get("object_filter"),
            "object_confidence": request.form.get("object_confidence", 0.5),
            "motion": request.form.get("motion", 0.2),
            "invert": request.form.get("invert", "false").lower()
            in ["true", "1", "t", "y", "yes", "on"],
            "dark": request.form.get("dark", "false").lower()
            in ["true", "1", "t", "y", "yes", "on"],
            "stealth": request.form.get("stealth", "false").lower()
            in ["true", "1", "t", "y", "yes", "on"],
            "browser": request.form.get("browser", "false").lower()
            in ["true", "1", "t", "y", "yes", "on"],
            "livecaption": request.form.get("livecaption", "false").lower()
            in ["true", "1", "t", "y", "yes", "on"],
            "danger": request.form.get("danger", "false").lower()
            in ["true", "1", "t", "y", "yes", "on"],
        }

        # If credentials were provided in the URL, move them into the template
        # auth fields so we don't persist passwords in URLs.
        url = updated_data.get("url") or ""
        parsed = urlparse(url)
        if parsed.username and not updated_data.get("auth_username"):
            updated_data["auth_username"] = parsed.username
        if parsed.password and not updated_data.get("auth_password"):
            updated_data["auth_password"] = parsed.password
        if parsed.username or parsed.password:
            host = parsed.hostname or ""
            netloc = host
            if parsed.port:
                netloc = f"{host}:{parsed.port}"
            updated_data["url"] = parsed._replace(netloc=netloc).geturl()
            url = updated_data["url"] or ""

        # If the submitted URL looks like an ONVIF device or base host, attempt
        # to autodetect the best snapshot/stream endpoint.
        if url and ("onvif" in url or urlparse(url).path in {"", "/"}):
            try:
                endpoints = routes.camera_discovery.autodetect_onvif_endpoints(
                    url,
                    username=updated_data.get("auth_username") or None,
                    password=updated_data.get("auth_password") or None,
                )
                if endpoints.get("snapshot"):
                    updated_data["url"] = endpoints["snapshot"]
                elif endpoints.get("stream"):
                    updated_data["url"] = endpoints["stream"]
            except Exception as exc:  # pragma: no cover - network issues
                logging.error("ONVIF autodetect failed for %s: %s", url, exc)

        for key in list(updated_data.keys()):
            if updated_data.get(key) is None:
                del updated_data[key]
        try:
            updated_data = routes.validate_update_data(updated_data)
        except ValueError as exc:
            if request.is_json:
                return jsonify({"error": str(exc)}), 400
            routes.flash(str(exc), "error")
            return redirect("/templates/" + template_name)
        routes.template_manager.save_template(template_name, updated_data)
        try:
            routes.scheduling.scheduler.remove_job(template_name)
        except LookupError as exc:
            logging.warning("Job removal failed for %s: %s", template_name, exc)
        routes.screenshots.create_blank_frame(template_name)
        routes.template_manager.get_template(template_name)
        try:
            seconds = int(updated_data.get("frequency", 30 * 60))
            routes.scheduling.scheduler.add_job(
                func=routes.scheduling.update_camera,
                trigger="interval",
                seconds=seconds,
                args=[template_name, updated_data],
                id=template_name,
                replace_existing=True,
            )
        except Exception as e:  # pragma: no cover - scheduler failure
            logging.error("job schedule error: %s", e)
        if request.is_json:
            return jsonify({"message": "Template updated successfully!"})
        return redirect("/templates/" + template_name)

    @bp.route("/status", endpoint="status")
    @routes.login_required
    def status():
        """Redirect to the Status tab under Settings."""

        return redirect(url_for("ui.settings", tab="status-tab"))

    @bp.route("/logs", endpoint="logs")
    @routes.login_required
    def logs():
        """Render the logs page."""

        return render_template("logs.html", page_title="Logs")

    @bp.route("/cost_summary", endpoint="cost_summary_page")
    @routes.login_required
    def cost_summary_page():
        """Show a summary of LLM costs."""

        templates = routes.template_manager.get_templates()
        costs = {
            name: routes.template_manager.get_llm_cost_estimate(name)
            for name in templates
        }
        start_time = int(
            routes.scheduling.system_metrics.get("start_time", time.time())
        )
        return render_template(
            "cost_summary.html",
            costs=costs,
            start_time=start_time,
            page_title="LLM Cost Summary",
        )

    @bp.route("/api/llm_cost_summary", endpoint="api_llm_cost_summary")
    @routes.login_required
    def api_llm_cost_summary():
        """Return cost summary data in JSON form."""

        start = request.args.get("start")
        end = request.args.get("end")
        group = request.args.get("group")
        summary, _, _, _ = routes.template_manager.get_llm_cost_summary(
            start_date=start, end_date=end, group=group
        )
        costs = {
            entry["name"]: {
                "tokens": entry["tokens"],
                "cost": entry["cost"],
                "calls": entry.get("calls", 0),
            }
            for entry in summary
        }
        return jsonify(costs)

    @bp.route(
        "/api/camera_log_summary/<string:template_name>",
        endpoint="api_camera_log_summary",
    )
    @routes.login_required
    def api_camera_log_summary(template_name: routes.TemplateName):
        """Return an error log summary for ``template_name``."""

        template_name = routes.validate_template_name(str(template_name))
        if template_name is None:
            routes.abort(404)
        summary = routes.scheduling.get_or_generate_camera_log_summary(template_name)
        if summary is None:
            return "", 204
        return jsonify({"summary": summary})

    @bp.route("/stream_logs", endpoint="stream_logs")
    @routes.login_required
    def stream_logs():
        """Serve server logs over SSE."""

        level = request.args.get("level")
        source = request.args.get("source")
        start_date = request.args.get("start_date")
        end_date = request.args.get("end_date")
        search = request.args.get("search")
        user_id = routes.session.get("user_id", 0)
        combo = (int(user_id), level or "", search or "")
        if combo in routes.active_log_streams:
            return Response(
                "event: duplicate\ndata: {}\n\n", mimetype="text/event-stream"
            )
        routes.active_log_streams[combo] = True

        def generate():
            try:
                while True:
                    logs = routes.read_logs_from_memory(
                        level=level,
                        source=source,
                        start_date=start_date,
                        end_date=end_date,
                        search=search,
                    )
                    logs = logs[:50]
                    yield f"data: {json.dumps(logs, default=str)}\n\n"
                    time.sleep(1)
            finally:
                routes.active_log_streams.pop(combo, None)

        return Response(
            routes.stream_with_context(generate()), mimetype="text/event-stream"
        )

    @bp.route("/search_suggestions", endpoint="search_suggestions")
    @routes.login_required
    def search_suggestions():
        """Return autocomplete suggestions for the search box."""

        query = request.args.get("q", "").lower()
        templates = routes.template_manager.get_templates()
        names = [t.get("name", "") for t in templates.values()]
        groups = routes.get_active_groups()
        docs_path = Path(__file__).resolve().parent.parent / "docs"
        doc_names = [
            f.stem for f in docs_path.glob("*.md") if f.name.lower() != "readme.md"
        ]
        suggestions: list[str] = []
        for item in names + groups + doc_names:
            if query and query not in item.lower():
                continue
            if item not in suggestions:
                suggestions.append(item)
            if len(suggestions) >= 10:
                break
        return jsonify(suggestions)

    return bp
