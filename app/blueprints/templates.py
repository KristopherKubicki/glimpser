from __future__ import annotations

import os
import socket
import tempfile
import typing
from urllib.parse import urlparse

from flask import Blueprint, Response, jsonify, redirect, request
from werkzeug.utils import secure_filename


def create_blueprint() -> Blueprint:
    """Create and return the templates management blueprint."""

    import app.routes as routes

    bp = Blueprint("templates", __name__)

    @bp.route("/upload_nav_icon", methods=["POST"])
    @routes.login_required
    def upload_nav_icon() -> Response:
        """Upload or select a navigation icon."""

        choice = request.form.get("logo_choice")
        if choice in {"img/glimpser_small.png", "img/glimpser.png"}:
            routes.update_setting("NAV_ICON", choice)
            routes.flash("Navigation logo updated", "success")
            return routes.redirect(routes.url_for("settings"))

        if "logo_file" not in request.files:
            routes.flash("No logo file provided", "error")
            return routes.redirect(routes.url_for("settings")), 400

        logo_file = request.files["logo_file"]
        if logo_file.filename == "":
            routes.flash("No logo file provided", "error")
            return routes.redirect(routes.url_for("settings")), 400

        if not routes.allowed_filename(
            logo_file.filename
        ) or not logo_file.filename.lower().endswith(".png"):
            routes.flash("Invalid file name", "error")
            return routes.redirect(routes.url_for("settings")), 400

        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            logo_file.save(temp_file.name)
            try:
                img = routes.Image.open(temp_file.name)
                w, h = img.size
                if h == 0 or not 2 <= w / h <= 10:
                    os.unlink(temp_file.name)
                    routes.flash("Invalid aspect ratio", "error")
                    return routes.redirect(routes.url_for("settings")), 400
            except Exception:
                os.unlink(temp_file.name)
                routes.flash("Invalid image file", "error")
                return routes.redirect(routes.url_for("settings")), 400

            dest_dir = os.path.join(routes.current_app.static_folder, "img")
            os.makedirs(dest_dir, exist_ok=True)
            dest_name = secure_filename(logo_file.filename)
            dest_path = os.path.join(dest_dir, dest_name)
            routes.shutil.move(temp_file.name, dest_path)
            routes.update_setting("NAV_ICON", f"img/{dest_name}")
        routes.flash("Navigation logo uploaded", "success")
        return routes.redirect(routes.url_for("settings"))

    @bp.route("/templates", methods=["GET", "POST", "DELETE"])
    @routes.login_required
    def manage_templates() -> Response:
        """Create, list and delete templates."""

        if request.method == "POST":
            data = request.get_json(silent=True) or {}
            template_name = routes.validate_template_name(str(data.get("name", "")))
            if template_name is None:
                routes.abort(404)
            url = data.get("url", "")
            if url and ("onvif" in url or urlparse(url).path in {"", "/"}):
                try:
                    endpoints = routes.camera_discovery.autodetect_onvif_endpoints(url)
                    if endpoints.get("snapshot"):
                        data["url"] = endpoints["snapshot"]
                    elif endpoints.get("stream"):
                        data["url"] = endpoints["stream"]
                except Exception:
                    pass
            if routes.template_manager.save_template(template_name, data):
                return routes.jsonify(
                    {"status": "success", "message": "Template saved"}
                )

        elif request.method == "GET":
            group = request.args.get("group")
            search_query = request.args.get("search", "").lower()
            templates = routes.template_manager.get_templates()

            filtered_templates: dict[str, typing.Any] = {}
            for name, template in templates.items():
                template_groups = template.get("groups", "").split(",")
                if (group == "all" or group in template_groups) and (
                    not search_query
                    or search_query in name.lower()
                    or search_query in template.get("url", "").lower()
                    or any(search_query in g.lower() for g in template_groups)
                ):
                    filtered_templates[name] = template

            return routes.jsonify(filtered_templates)

        elif request.method == "DELETE":
            data = request.get_json(silent=True) or {}
            template_name = routes.validate_template_name(str(data.get("name", "")))
            if template_name is None:
                routes.abort(404)
            if routes.template_manager.delete_template(template_name):
                return routes.jsonify(
                    {"status": "success", "message": "Template deleted"}
                )
            return (
                routes.jsonify({"status": "failure", "message": "Template not found"}),
                404,
            )

        return routes.jsonify({"status": "ignored"})

    @bp.route("/templates/<string:template_name>")
    @routes.login_required
    def template_details(template_name: routes.TemplateName) -> Response:
        """Render details for a specific template."""

        template_name = routes.validate_template_name(str(template_name))
        if template_name is None:
            routes.abort(404)

        templates = routes.template_manager.get_templates()
        details = templates.get(template_name)
        if details is None:
            routes.abort(404)
        lscreenshots = routes.template_manager.get_screenshots_for_template(
            template_name
        )
        lvideos = routes.template_manager.get_videos_for_template(template_name)
        object_tokens = ["person", "car", "dog", "cat", "truck", "bus", "bicycle"]
        return routes.render_template(
            "template_details.html",
            template_name=template_name,
            template_details=details,
            screenshots=lscreenshots,
            videos=lvideos,
            object_tokens=object_tokens,
            clip_model=routes.CLIP_MODEL_NAME,
            clip_gpu=routes.clip_gpu_available(),
            page_title="Camera Details",
        )

    @bp.route("/generate_prompt/<string:template_name>", methods=["POST"])
    @routes.login_required
    def generate_prompt_route(template_name: routes.TemplateName) -> Response:
        """Return a suggested caption prompt for ``template_name``."""

        template_name = routes.validate_template_name(str(template_name))
        if template_name is None:
            routes.abort(404)

        prompt = routes.prompt_optimizer.generate_prompt(template_name)
        return routes.jsonify({"prompt": prompt})

    @bp.route("/suggest_fix/<string:template_name>", methods=["POST"])
    @routes.login_required
    def suggest_fix_route(template_name: routes.TemplateName) -> Response:
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
        return routes.jsonify(info)

    @bp.route("/camera_diagnostics/<string:template_name>")
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
            ip = socket.gethostbyname(host)
        except Exception:
            ip = host

        data: dict[str, typing.Any] = {"ip": ip}

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

        return routes.jsonify(data)

    @bp.route("/update_template/<string:template_name>", methods=["POST"])
    @routes.login_required
    def update_template(template_name: routes.TemplateName) -> Response:
        """Update template configuration and reschedule its job."""

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
            in {"true", "1", "t", "y", "yes", "on"},
            "dark": request.form.get("dark", "false").lower()
            in {"true", "1", "t", "y", "yes", "on"},
            "headless": request.form.get("headless", "false").lower()
            in {"true", "1", "t", "y", "yes", "on"},
            "stealth": request.form.get("stealth", "false").lower()
            in {"true", "1", "t", "y", "yes", "on"},
            "browser": request.form.get("browser", "false").lower()
            in {"true", "1", "t", "y", "yes", "on"},
            "livecaption": request.form.get("livecaption", "false").lower()
            in {"true", "1", "t", "y", "yes", "on"},
            "danger": request.form.get("danger", "false").lower()
            in {"true", "1", "t", "y", "yes", "on"},
        }

        lremoves = [k for k, v in updated_data.items() if v is None]
        for k in lremoves:
            del updated_data[k]

        try:
            updated_data = routes.validate_update_data(updated_data)
        except ValueError as exc:
            if request.is_json:
                return routes.jsonify({"error": str(exc)}), 400
            routes.flash(str(exc), "error")
            return routes.redirect("/templates/" + template_name)

        routes.template_manager.save_template(template_name, updated_data)

        try:
            routes.scheduling.scheduler.remove_job(template_name)
        except Exception:
            pass
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
        except Exception as exc:
            routes.logging.error("job schedule error: %s", exc)

        if request.is_json:
            return routes.jsonify({"message": "Template updated successfully!"})

        return routes.redirect("/templates/" + template_name)

    return bp
