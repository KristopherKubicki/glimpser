from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from flask import Blueprint, jsonify, request
from sqlalchemy import text


def create_blueprint() -> Blueprint:
    """Create and return the status blueprint."""

    import app.routes as routes

    bp = Blueprint("status", __name__)

    @bp.route("/health")
    @routes.login_required
    @routes.profile_route("/health")
    def health_check():
        scheduler_status = "failed"
        free_gb = 0

        metrics = routes.scheduling.get_system_metrics()

        cpu_threshold = 80
        memory_threshold = 80
        thread_threshold = 100
        open_file_threshold = 1024
        disk_threshold = 95

        error_messages: list[str] = []
        is_nominal = True

        if metrics["cpu_usage"] >= cpu_threshold:
            is_nominal = False
            error_messages.append(f"CPU usage is high: {metrics['cpu_usage']}%")
        if metrics["memory_usage"] >= memory_threshold:
            is_nominal = False
            error_messages.append(f"Memory usage is high: {metrics['memory_usage']}%")
        if metrics["thread_count"] >= thread_threshold:
            is_nominal = False
            error_messages.append(f"Thread count is high: {metrics['thread_count']}")
        if metrics["open_files"] >= open_file_threshold:
            is_nominal = False
            error_messages.append(f"Too many open files: {metrics['open_files']}")
        if metrics["disk_usage"] >= disk_threshold:
            is_nominal = False
            error_messages.append(f"Disk usage is high: {metrics['disk_usage']}%")

        try:
            if len(metrics["uptime"]) < 9 and "0h 0m " in metrics["uptime"]:
                is_nominal = False
                error_messages.append("System just started, still initializing")
        except Exception:
            is_nominal = False
            error_messages.append("Error getting system uptime")

        try:
            session = routes.SessionLocal()
            session.execute(text("SELECT 1"))
            session.close()
            db_status = "connected"
        except Exception:
            is_nominal = False
            db_status = "disconnected"
            error_messages.append("Database connection failed")

        try:
            scheduler_status = (
                "running" if routes.scheduling.scheduler.running else "stopped"
            )
            if scheduler_status != "running":
                is_nominal = False
                error_messages.append("Scheduler is not running")
        except Exception:
            is_nominal = False
            scheduler_status = "failed"
            error_messages.append("Error checking scheduler status")

        return (
            jsonify(
                {
                    "status": "healthy" if is_nominal else "degraded",
                    "metrics": metrics,
                    "nominal": is_nominal,
                    "database": db_status,
                    "scheduler": scheduler_status,
                    "free_disk_space_gb": free_gb,
                    "error_messages": error_messages,
                }
            ),
            200,
        )

    @bp.route("/danger_status")
    @routes.login_required
    @routes.profile_route("/danger_status")
    def danger_status():
        port_open = routes.is_chrome_debug_port_open("127.0.0.1", 9222)
        idle = not routes.check_user_activity(timeout=1)
        enabled = routes.config.get_setting("DANGER_MODE", "True") == "True"
        browser_path = routes.get_chrome_path()
        patched = not routes.shortcuts_need_patch()
        return jsonify(
            {
                "port_open": port_open,
                "idle": idle,
                "enabled": enabled,
                "ready": port_open and idle and enabled,
                "browser": (os.path.basename(browser_path) if browser_path else None),
                "path": browser_path,
                "version": (
                    routes.get_chrome_version(browser_path) if browser_path else None
                ),
                "shortcut": str(routes.first_shortcut_path() or ""),
                "patched": patched,
            }
        )

    @bp.route("/captions_status")
    @routes.login_required
    def captions_status():
        group = request.args.get("group")
        if group and group != "all":
            templates = routes.template_manager.get_templates()
            latest_time = None
            caption = ""
            for name, tmpl in templates.items():
                groups = [g.strip() for g in tmpl.get("groups", "").split(",")]
                if group not in groups:
                    continue
                t = tmpl.get("last_caption_time")
                if not t:
                    continue
                try:
                    dt = datetime.strptime(t, "%Y-%m-%d %H:%M:%S")
                except Exception:
                    continue
                if not latest_time or dt > latest_time:
                    latest_time = dt
                    caption = tmpl.get("last_caption", "")
            if latest_time:
                return jsonify(
                    {
                        "caption": caption,
                        "timestamp": latest_time.strftime("%Y-%m-%d %H:%M:%S"),
                    }
                )

        caption = ""
        timestamp = ""
        session_db = routes.SessionLocal()
        try:
            rec = (
                session_db.query(routes.Summary)
                .order_by(routes.Summary.timestamp.desc())
                .first()
            )
            if rec:
                try:
                    data = json.loads(getattr(rec, "content", ""))
                    if data:
                        caption = next(iter(data.values()))
                except Exception:
                    caption = getattr(rec, "content", "")
                ts = getattr(rec, "timestamp", None)
                if ts is not None:
                    timestamp = datetime.utcfromtimestamp(ts).strftime(
                        "%Y-%m-%dT%H:%M:%SZ"
                    )
        except Exception as e:  # pragma: no cover - unexpected DB errors
            routes.logging.error("error retrieving captions status: %s", e)
        finally:
            session_db.close()

        return jsonify({"caption": caption, "timestamp": timestamp})

    @bp.route("/discovery_status")
    @routes.login_required
    @routes.profile_route("/discovery_status")
    def discovery_status():
        return jsonify(routes.scheduling.get_discovery_status())

    @bp.route("/discover/subnets")
    @routes.login_required
    def discover_subnets():
        nets = [str(n) for n in routes.camera_discovery._local_subnets()]
        nets.append("internet")
        return jsonify(nets)

    @bp.route("/toggle_discovery", methods=["POST"])
    @routes.login_required
    @routes.profile_route("/toggle_discovery")
    def toggle_discovery():
        try:
            job = routes.scheduling.scheduler.get_job("background_discovery")
            if job:
                routes.scheduling.stop_discovery()
                routes.update_setting("DISCOVERY_AUTOSTART", "False", restart=False)
                return jsonify({"status": "stopped"})
            routes.scheduling.schedule_discovery()
            routes.update_setting("DISCOVERY_AUTOSTART", "True", restart=False)
            return jsonify({"status": "running"})
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500

    @bp.route("/toggle_chyron", methods=["POST"])
    @routes.login_required
    @routes.profile_route("/toggle_chyron")
    def toggle_chyron():
        try:
            current = routes.config.get_setting("CHYRON_SPEED", "0")
            new_speed = "0" if str(current) != "0" else "240"
            routes.update_setting("CHYRON_SPEED", new_speed)
            return jsonify({"speed": int(new_speed)})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    return bp
