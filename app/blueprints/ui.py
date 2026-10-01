from __future__ import annotations

import hashlib
import io
import json
import logging
import os
import re
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

from flask import (
    Blueprint,
    Response,
    abort,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from flask_login import current_user

from app.viewer_policy import VIEWER_CONFIG, dashboard_matches, viewer_template

_MISSING_SCREENSHOT_LOG_INTERVAL_SECONDS = 300
_missing_screenshot_log_ts: dict[str, float] = {}

# Tiny per-process cache for the templates JSON payload. The templates UI polls
# frequently; this keeps the endpoint responsive under load and enables ETag/304.
_TEMPLATES_JSON_CACHE: dict[tuple[str, str, str, bool, str], dict[str, object]] = {}
_TEMPLATES_JSON_CACHE_TTL_SECONDS = 1.0

_GOOGLE_OAUTH_STATE_TTL_SECONDS = 30 * 60
_google_oauth_states: dict[str, tuple[str, float]] = {}
_google_oauth_states_lock = threading.Lock()
_PTZ_DIRECTION_VECTORS: dict[str, tuple[float, float, float]] = {
    "up": (0.0, 0.7, 0.0),
    "down": (0.0, -0.7, 0.0),
    "left": (-0.7, 0.0, 0.0),
    "right": (0.7, 0.0, 0.0),
    "up_left": (-0.6, 0.6, 0.0),
    "up_right": (0.6, 0.6, 0.0),
    "down_left": (-0.6, -0.6, 0.0),
    "down_right": (0.6, -0.6, 0.0),
    "zoom_in": (0.0, 0.0, 0.7),
    "zoom_out": (0.0, 0.0, -0.7),
}
_PTZ_LENS_DIRECTIONS = {
    "focus_near",
    "focus_far",
    "iris_open",
    "iris_close",
}


def _store_google_oauth_state(state: str, profile: str) -> None:
    now = time.monotonic()
    cutoff = now - _GOOGLE_OAUTH_STATE_TTL_SECONDS
    with _google_oauth_states_lock:
        for k, (_, ts) in list(_google_oauth_states.items()):
            if ts < cutoff:
                _google_oauth_states.pop(k, None)
        _google_oauth_states[state] = (profile, now)


def _pop_google_oauth_profile(state: str) -> str | None:
    if not state:
        return None
    now = time.monotonic()
    with _google_oauth_states_lock:
        entry = _google_oauth_states.pop(state, None)

    if not entry:
        return None

    profile, ts = entry
    if now - ts > _GOOGLE_OAUTH_STATE_TTL_SECONDS:
        return None

    return profile


def _log_missing_screenshot(name: str) -> None:
    """Rate-limit noisy missing-screenshot warnings per source."""

    now = time.monotonic()
    key = (name or "unknown").strip() or "unknown"
    last = _missing_screenshot_log_ts.get(key, 0.0)
    if now - last >= _MISSING_SCREENSHOT_LOG_INTERVAL_SECONDS:
        _missing_screenshot_log_ts[key] = now
        logging.warning("Unable to serve screenshot for %s", key)


def _normalize_ptz_presets(raw: object) -> list[dict[str, str]]:
    """Return PTZ presets as ``[{token, name}, ...]``."""

    if not raw:
        return []
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError):
            return []
    if not isinstance(raw, list):
        return []

    presets: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        token = str(item.get("token") or "").strip()
        if not token:
            continue
        name = str(item.get("name") or token).strip() or token
        presets.append({"token": token, "name": name})
    return presets


def _looks_like_generic_preset_name(name: str, token: str) -> bool:
    """Return ``True`` when a preset name is just vendor placeholder noise."""

    normalized_name = str(name or "").strip().lower()
    normalized_token = str(token or "").strip().lower()
    if not normalized_name:
        return True
    if normalized_name == normalized_token:
        return True
    if (
        normalized_name.startswith("preset ")
        and normalized_name[7:].strip() == normalized_token
    ):
        return True
    return False


def _merge_ptz_presets(
    discovered_raw: object, existing_raw: object | None = None
) -> list[dict[str, str]]:
    """Return discovered presets while preserving curated names for matching tokens."""

    discovered = _normalize_ptz_presets(discovered_raw)
    existing = _normalize_ptz_presets(existing_raw)
    if not discovered:
        return existing
    if not existing:
        return discovered

    existing_by_token = {
        str(item.get("token") or "").strip(): str(item.get("name") or "").strip()
        for item in existing
        if str(item.get("token") or "").strip()
    }
    merged: list[dict[str, str]] = []
    for item in discovered:
        token = str(item.get("token") or "").strip()
        name = str(item.get("name") or token).strip() or token
        existing_name = existing_by_token.get(token, "")
        if existing_name and _looks_like_generic_preset_name(name, token):
            name = existing_name
        merged.append({"token": token, "name": name})
    return merged


def _ptz_state_from_template(details: dict[str, object] | None) -> dict[str, object]:
    """Return UI-friendly PTZ metadata for a template."""

    details = details or {}
    presets = _normalize_ptz_presets(details.get("ptz_presets"))
    enabled = bool(details.get("ptz_enabled")) and bool(
        details.get("ptz_profile_token")
    )
    try:
        speed = float(details.get("ptz_speed") or 0.6)
    except (TypeError, ValueError):
        speed = 0.6
    speed = max(0.1, min(speed, 1.0))
    try:
        duration_ms = int(details.get("ptz_duration_ms") or 450)
    except (TypeError, ValueError):
        duration_ms = 450
    duration_ms = max(100, min(duration_ms, 10000))
    vendor_driver = str(details.get("ptz_vendor_driver") or "").strip()
    return {
        "enabled": enabled,
        "service": str(details.get("ptz_service") or "").strip(),
        "profile_token": str(details.get("ptz_profile_token") or "").strip(),
        "profile_name": str(details.get("ptz_profile_name") or "").strip(),
        "presets": presets,
        "speed": speed,
        "duration_ms": duration_ms,
        "vendor_driver": vendor_driver,
        "supports_lens_controls": vendor_driver == "uid_cgi",
    }


def _build_ptz_template_updates(
    endpoints: dict[str, object], existing: dict[str, object] | None = None
) -> dict[str, object]:
    """Return PTZ template updates while preserving existing state when needed."""

    existing = existing or {}
    existing_presets = _normalize_ptz_presets(existing.get("ptz_presets"))
    presets = _merge_ptz_presets(
        endpoints.get("ptz_presets"), existing.get("ptz_presets")
    )
    ptz_service = str(
        endpoints.get("ptz_service") or existing.get("ptz_service") or ""
    ).strip()
    profile_token = str(
        endpoints.get("profile_token") or existing.get("ptz_profile_token") or ""
    ).strip()
    profile_name = str(
        endpoints.get("profile_name") or existing.get("ptz_profile_name") or ""
    ).strip()
    vendor_driver = str(
        endpoints.get("ptz_vendor_driver") or existing.get("ptz_vendor_driver") or ""
    ).strip()
    enabled = bool(ptz_service) and bool(profile_token)
    return {
        "ptz_enabled": enabled,
        "ptz_service": ptz_service,
        "ptz_profile_token": profile_token,
        "ptz_profile_name": profile_name,
        "ptz_presets": json.dumps(
            presets if presets else existing_presets, separators=(",", ":")
        ),
        "ptz_vendor_driver": vendor_driver,
    }


def _probe_onvif_metadata(
    url: str,
    *,
    username: str | None = None,
    password: str | None = None,
    replace_url: bool = False,
    existing: dict[str, object] | None = None,
) -> dict[str, object]:
    """Probe ONVIF metadata without forcing the capture URL to change."""

    from app import routes

    endpoints = routes.camera_discovery.autodetect_onvif_endpoints(
        url,
        username=username,
        password=password,
    )
    endpoints["ptz_vendor_driver"] = routes.camera_discovery.detect_ptz_vendor_driver(
        url,
        username=username,
        password=password,
    )
    updates = _build_ptz_template_updates(endpoints, existing=existing)
    if replace_url:
        if endpoints.get("snapshot"):
            updates["url"] = str(endpoints["snapshot"])
        elif endpoints.get("stream"):
            updates["url"] = str(endpoints["stream"])
    return updates


def create_blueprint() -> Blueprint:
    """Create and return the UI blueprint with web routes."""

    from app import routes
    from app.utils import recovery
    from app.utils.sun_calibration import (
        bearing_to_cardinal,
        build_sun_calibration_evidence,
        estimate_camera_bearing,
        sun_frame_payload,
    )
    from app.utils.validators import validate_group_name

    bp = Blueprint("ui", __name__)
    non_sun_groups = {
        "archive",
        "bodycam",
        "cosmic",
        "dashboard",
        "emergency",
        "flights",
        "health",
        "map",
        "maps",
        "network",
        "ops",
        "plants",
        "ptz",
        "source-stale",
        "telemetry",
    }
    non_sun_name_tokens = (
        "aqi",
        "bingmaps",
        "fast.com",
        "fires",
        "flightradar",
        "googlemaps",
        "hubitat",
        "lightning",
        "police",
        "redfin",
        "sigalert",
        "waze",
        "wind",
        "zoomearth",
    )
    non_sun_direction_tokens = ("interior", "plant")

    def _calibration_float(value: object) -> float | None:
        try:
            if value in {None, ""}:
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    def _calibration_screenshots_for_template(
        name: str, *, max_count: int | None = None
    ) -> list[str]:
        camera_dir = Path(routes.SCREENSHOT_DIRECTORY) / name
        if not camera_dir.exists():
            return []
        filenames = [
            item.name
            for item in camera_dir.iterdir()
            if item.is_file()
            and item.name.startswith(f"{name}_")
            and item.name.endswith(".png")
            and ".tmp" not in item.name
            and ".partial" not in item.name
        ]
        filenames = routes.template_manager.sort_canonical_screenshot_filenames(
            name, filenames, reverse=True
        )
        if max_count is None:
            return filenames
        return filenames[:max_count]

    def _calibration_camera_payload(name: str, template: dict[str, object]) -> dict:
        latitude = _calibration_float(template.get("camera_latitude"))
        longitude = _calibration_float(template.get("camera_longitude"))
        screenshots = _calibration_screenshots_for_template(name)
        groups = [
            group.strip()
            for group in str(template.get("groups") or "").split(",")
            if group.strip()
        ]
        fov = _calibration_float(template.get("view_horizontal_fov_degrees"))
        has_location = latitude is not None and longitude is not None
        frame_count = len(screenshots)
        lower_name = name.lower()
        lower_groups = {group.lower() for group in groups}
        lower_direction = str(template.get("view_direction") or "").lower()
        is_non_sun_source = (
            bool(non_sun_groups.intersection(lower_groups))
            or any(token in lower_name for token in non_sun_name_tokens)
            or any(token in lower_direction for token in non_sun_direction_tokens)
        )
        if not has_location:
            calibration_reason = "missing camera coordinates"
        elif frame_count < 1:
            calibration_reason = "no history frames"
        elif is_non_sun_source:
            calibration_reason = "map/dashboard source"
        else:
            calibration_reason = "ready"
        return {
            "name": name,
            "groups": groups,
            "location_label": str(template.get("camera_location_label") or ""),
            "latitude": latitude,
            "longitude": longitude,
            "has_location": has_location,
            "frame_count": frame_count,
            "calibration_candidate": calibration_reason == "ready",
            "calibration_reason": calibration_reason,
            "current_bearing_degrees": _calibration_float(
                template.get("view_bearing_degrees")
            ),
            "current_direction": str(template.get("view_direction") or ""),
            "horizontal_fov_degrees": fov or 90.0,
            "pose_confidence": str(template.get("view_pose_confidence") or ""),
            "pose_evidence": str(template.get("view_pose_evidence") or ""),
        }

    def _calibration_best_frame(
        name: str,
        template: dict[str, object],
        *,
        history_limit: int = 1500,
    ) -> dict[str, object] | None:
        latitude = _calibration_float(template.get("camera_latitude"))
        longitude = _calibration_float(template.get("camera_longitude"))
        if latitude is None or longitude is None:
            return None

        best_frame: dict[str, object] | None = None
        for filename in _calibration_screenshots_for_template(
            name, max_count=history_limit
        ):
            payload = sun_frame_payload(name, filename, latitude, longitude)
            if not payload:
                continue
            if best_frame is None or (
                int(payload.get("score") or 0),
                str(payload.get("captured_at") or ""),
            ) > (
                int(best_frame.get("score") or 0),
                str(best_frame.get("captured_at") or ""),
            ):
                best_frame = payload

        if best_frame:
            best_frame["image_url"] = url_for(
                "media.view_screenshot", name=name, filename=best_frame["filename"]
            )
        return best_frame

    def _calibration_status(camera: dict[str, object]) -> dict[str, object]:
        has_operator_bearing = camera.get(
            "current_bearing_degrees"
        ) is not None and str(camera.get("pose_confidence") or "") in {
            "operator",
            "calibrated",
        }
        has_any_bearing = camera.get("current_bearing_degrees") is not None
        if has_operator_bearing:
            return {
                "key": "calibrated",
                "label": "Calibrated",
                "needs_calibration": False,
            }
        if has_any_bearing:
            return {
                "key": "review",
                "label": "Review estimate",
                "needs_calibration": True,
            }
        return {
            "key": "needs_bearing",
            "label": "Needs bearing",
            "needs_calibration": True,
        }

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
        rotator = request.args.get("rotator")
        force_all_rotator = rotator == "all"
        selected_camera = None
        selected_group = None

        # In explicit all-rotator mode, ignore any stale camera/group query
        # values so the client always receives the full template set.
        if force_all_rotator:
            camera = None
            group = None

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

        routes.logging.info(
            "live page request camera=%s group=%s rotator=%s templates=%d",
            camera,
            group,
            rotator,
            len(templates or {}),
        )
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

    @bp.route("/client_beacon", methods=["POST"], endpoint="client_beacon")
    @routes.login_required
    def client_beacon():
        """Lightweight client beacon for debugging UI state."""

        payload = request.get_json(silent=True) or {}
        routes.logging.info(
            "client_beacon ip=%s path=%s event=%s data=%s",
            request.remote_addr,
            str(payload.get("path") or ""),
            str(payload.get("event") or ""),
            str(payload.get("data") or ""),
        )
        return ("", 204)

    @bp.route("/kiosk_indicators", methods=["POST"])
    def ingest_kiosk_indicator():
        """Accept only dedicated, authenticated Hubitat indicator signals."""
        from app.utils import kiosk_indicators

        if not kiosk_indicators.authenticated(request.headers.get("Authorization", "")):
            abort(401)
        if request.content_length is None or request.content_length > 2048:
            abort(413)
        try:
            kiosk_indicators.accept(request.get_json(silent=True), time.time())
        except (ValueError, TypeError, OverflowError):
            abort(400)
        return jsonify({"ok": True})

    @bp.route("/kiosk_indicators", methods=["GET"])
    @routes.login_required
    def kiosk_indicators():
        """Return fresh room-scoped indicators without private message content."""
        from app.utils.kiosk_indicators import snapshot

        profile = request.args.get("profile", "")
        if profile not in {"office", "living"}:
            abort(400)
        response = jsonify(snapshot(profile))
        response.headers["Cache-Control"] = "no-store"
        return response

    # Per-process heartbeat state is deliberately reset on server restart.
    # The kiosk-side monitor grants a startup grace period when age is unknown.
    kiosk_heartbeats = {}

    @bp.route("/kiosk_health", methods=["GET", "POST"])
    @routes.login_required
    def kiosk_health():
        """Report browser rendering-loop activity for the requesting kiosk only."""
        import time

        profile = request.args.get("profile", "")
        if profile not in {"office", "living"}:
            abort(400)
        key = (request.remote_addr, profile)
        now = time.monotonic()
        # Bound retained state even when many authenticated clients visit.
        for old_key, stamp in list(kiosk_heartbeats.items()):
            if now - stamp > 3600:
                kiosk_heartbeats.pop(old_key, None)
        if request.method == "POST":
            if len(kiosk_heartbeats) < 256 or key in kiosk_heartbeats:
                kiosk_heartbeats[key] = now
            return ("", 204)
        stamp = kiosk_heartbeats.get(key)
        response = jsonify({"age_seconds": round(now - stamp, 1) if stamp else None})
        response.headers["Cache-Control"] = "no-store"
        return response

    @bp.route("/clock", endpoint="clock_page")
    @routes.login_required
    def clock_page():
        """Render a standalone clock page."""

        return render_template("clock.html", page_title="Clock")

    @bp.route("/sun-calibration", endpoint="sun_calibration")
    @routes.login_required
    def sun_calibration():
        """Render the operator game for sun-based camera bearing calibration."""

        return render_template("sun_calibration.html", page_title="Sun Calibration")

    @bp.route("/api/sun-calibration/cameras", endpoint="sun_calibration_cameras")
    @routes.login_required
    def sun_calibration_cameras():
        """Return cameras that can participate in sun bearing calibration."""

        templates = routes.template_manager.get_templates()
        cameras = [
            _calibration_camera_payload(name, template)
            for name, template in sorted(templates.items())
        ]
        cameras.sort(
            key=lambda item: (
                not bool(item["calibration_candidate"]),
                not bool(item["has_location"]),
                not bool(item["frame_count"]),
                str(item["name"]).lower(),
            )
        )
        return jsonify({"cameras": cameras})

    @bp.route("/api/sun-calibration/queue", endpoint="sun_calibration_queue")
    @routes.login_required
    def sun_calibration_queue():
        """Return the ranked operator queue for sun bearing calibration."""

        try:
            history_limit = int(request.args.get("history_limit", 1500))
        except (TypeError, ValueError):
            history_limit = 1500
        history_limit = max(100, min(history_limit, 3000))

        templates = routes.template_manager.get_templates()
        queue = []
        for name, template in sorted(templates.items()):
            camera = _calibration_camera_payload(name, template)
            if not camera["calibration_candidate"]:
                continue
            best_frame = _calibration_best_frame(
                name, template, history_limit=history_limit
            )
            status = _calibration_status(camera)
            queue.append(
                {
                    "camera": camera,
                    "best_frame": best_frame,
                    "status": status,
                }
            )

        queue.sort(
            key=lambda item: (
                not bool(item["status"]["needs_calibration"]),
                -int((item["best_frame"] or {}).get("score") or 0),
                str(item["camera"]["name"]).lower(),
            )
        )
        return jsonify({"queue": queue})

    @bp.route(
        "/api/sun-calibration/<string:template_name>/frames",
        endpoint="sun_calibration_frames",
    )
    @routes.login_required
    def sun_calibration_frames(template_name: routes.TemplateName):
        """Return recent history frames with computed sun position metadata."""

        raw_name = str(template_name)
        template_name = routes.validate_template_name(raw_name)
        if template_name is None:
            return jsonify({"error": "invalid_template"}), 400
        template = routes.template_manager.get_template(template_name)
        if not template:
            routes.abort(404)

        latitude = _calibration_float(template.get("camera_latitude"))
        longitude = _calibration_float(template.get("camera_longitude"))
        if latitude is None or longitude is None:
            return jsonify({"error": "missing_camera_location"}), 400

        try:
            limit = int(request.args.get("limit", 48))
        except (TypeError, ValueError):
            limit = 48
        limit = max(1, min(limit, 100))
        try:
            history_limit = int(request.args.get("history_limit", 720))
        except (TypeError, ValueError):
            history_limit = 720
        history_limit = max(limit, min(history_limit, 3000))

        frames = []
        for filename in _calibration_screenshots_for_template(
            template_name, max_count=history_limit
        ):
            payload = sun_frame_payload(template_name, filename, latitude, longitude)
            if not payload:
                continue
            payload["image_url"] = url_for(
                "media.view_screenshot", name=template_name, filename=filename
            )
            frames.append(payload)

        frames.sort(
            key=lambda item: (
                int(item.get("score") or 0),
                str(item.get("captured_at") or ""),
            ),
            reverse=True,
        )
        frames = frames[:limit]
        return jsonify(
            {
                "camera": _calibration_camera_payload(template_name, template),
                "frames": frames,
            }
        )

    @bp.route(
        "/api/sun-calibration/<string:template_name>/bearing",
        methods=["POST"],
        endpoint="sun_calibration_bearing",
    )
    @routes.login_required
    def sun_calibration_bearing(template_name: routes.TemplateName):
        """Save a camera bearing inferred from a sun position observation."""

        template_name = routes.validate_template_name(str(template_name))
        if template_name is None:
            return jsonify({"error": "invalid_template"}), 400
        template = routes.template_manager.get_template(template_name)
        if not template:
            routes.abort(404)

        data = request.get_json(silent=True) or {}
        filename = str(data.get("filename") or "")
        frame_position = str(data.get("frame_position") or "")
        note = str(data.get("note") or "").strip()

        screenshots = set(_calibration_screenshots_for_template(template_name))
        if filename not in screenshots:
            return jsonify({"error": "invalid_frame"}), 400

        latitude = _calibration_float(template.get("camera_latitude"))
        longitude = _calibration_float(template.get("camera_longitude"))
        if latitude is None or longitude is None:
            return jsonify({"error": "missing_camera_location"}), 400

        try:
            horizontal_fov = float(
                data.get("horizontal_fov_degrees")
                or template.get("view_horizontal_fov_degrees")
                or 90.0
            )
        except (TypeError, ValueError):
            return jsonify({"error": "invalid_horizontal_fov"}), 400

        payload = sun_frame_payload(template_name, filename, latitude, longitude)
        if not payload:
            return jsonify({"error": "invalid_frame_timestamp"}), 400

        try:
            bearing = estimate_camera_bearing(
                float(payload["sun_azimuth_degrees"]),
                horizontal_fov,
                frame_position,
            )
        except ValueError as exc:
            return jsonify({"error": str(exc).replace(" ", "_")}), 400

        direction = bearing_to_cardinal(bearing)
        evidence = build_sun_calibration_evidence(
            filename=filename,
            captured_at=str(payload["captured_at"]),
            sun_azimuth_degrees=float(payload["sun_azimuth_degrees"]),
            sun_elevation_degrees=float(payload["sun_elevation_degrees"]),
            frame_position=frame_position,
            horizontal_fov_degrees=horizontal_fov,
            note=note,
        )
        description = str(template.get("view_description") or "").strip()
        if not description:
            description = "Camera bearing calibrated from historical sun position."

        updates = {
            "view_bearing_degrees": bearing,
            "view_direction": direction,
            "view_horizontal_fov_degrees": horizontal_fov,
            "view_pose_confidence": "operator",
            "view_pose_evidence": evidence,
            "view_description": description,
            "view_metadata_updated": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        }
        if not routes.template_manager.save_template(template_name, updates):
            return jsonify({"error": "save_failed"}), 500

        return jsonify(
            {
                "ok": True,
                "bearing_degrees": bearing,
                "direction": direction,
                "evidence": evidence,
            }
        )

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
                    data.update(
                        _probe_onvif_metadata(
                            url,
                            username=data.get("auth_username") or None,
                            password=data.get("auth_password") or None,
                            replace_url=True,
                        )
                    )
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
            viewer = request.args.get("viewer") == "1" or session_user is None
            dashboard = request.args.get("dashboard", "")
            cache_key = (user_id, group, search_query, viewer, dashboard)
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
                if not dashboard_matches(dashboard, name, template):
                    continue
                if viewer:
                    template = viewer_template(name, template)
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
        ptz_state = _ptz_state_from_template(template_details)
        return render_template(
            "template_details.html",
            template_name=template_name,
            template_details=template_details,
            ptz_state=ptz_state,
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
            seconds = 60 * max(1, int(template.get("frequency") or 30))
            routes.scheduling.scheduler.add_job(
                func=routes.scheduling.update_camera,
                trigger="interval",
                seconds=seconds,
                args=[template_name, template],
                id=template_name,
                executor=routes.scheduling.camera_executor(template),
                max_instances=1,
                coalesce=True,
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

    @bp.route("/xpath_health", endpoint="xpath_health")
    @routes.login_required
    def xpath_health():
        """Render a health report for configured popup/dedicated XPaths."""

        templates = routes.template_manager.get_templates()
        screenshots_root = Path(routes.SCREENSHOT_DIRECTORY)
        image_exts = {".png", ".jpg", ".jpeg", ".webp"}

        def _norm_xpath(xpath: str | None) -> str:
            return " ".join((xpath or "").split())

        def _xpath_risks(xpath: str | None) -> list[str]:
            norm = _norm_xpath(xpath)
            if not norm:
                return []
            lower = norm.lower()
            risks: list[str] = []
            if norm in {"//iframe", "//p", "//table", "//article", "//main"}:
                risks.append("overly generic selector")
            if "uzbvz" in lower:
                risks.append("hashed class name (likely unstable)")
            if "contains(@class,'jss" in lower or 'contains(@class,"jss' in lower:
                risks.append("JSS-generated class name (likely unstable)")
            if "contains(@class,'css-" in lower or 'contains(@class,"css-' in lower:
                risks.append("CSS-hash class name (likely unstable)")
            if "contains(@id,'ember" in lower or 'contains(@id,"ember' in lower:
                risks.append("ember-generated id (likely unstable)")
            if (
                "contains(@name, 'welcome')" in lower
                or 'contains(@name,"welcome")' in lower
            ):
                risks.append("welcome-popup selector is often transient")
            if "leaflet-pane" in lower:
                risks.append("targets map tile pane (can miss overlays)")
            if norm.startswith("//*"):
                risks.append("global wildcard selector")
            # Commonly leads to selecting the wrong element when multiple iframes exist.
            if norm == "//iframe":
                risks.append("iframe selector without @src constraint is fragile")
            elif (
                norm.startswith("//iframe[")
                and "@src" not in lower
                and "contains(@src" not in lower
            ):
                risks.append("iframe selector without @src constraint is fragile")
            return risks

        rows: list[dict[str, object]] = []
        tiny_count = 0
        issue_count = 0

        for name in sorted(n for n in templates.keys() if n):
            template = templates.get(name, {})
            popup_xpath = (template.get("popup_xpath") or "").strip()
            dedicated_xpath = (template.get("dedicated_xpath") or "").strip()

            issues: list[str] = []
            for risk in _xpath_risks(popup_xpath):
                issues.append(f"popup_xpath: {risk}")
            for risk in _xpath_risks(dedicated_xpath):
                issues.append(f"dedicated_xpath: {risk}")

            suggestions: list[str] = []
            latest_tiny = False
            latest_name = ""
            latest_age = ""
            latest_dims = ""
            latest_kb: float | None = None

            shot_dir = screenshots_root / routes.secure_filename(name)
            latest_path = None
            if shot_dir.exists() and shot_dir.is_dir():
                latest_path = max(
                    (
                        p
                        for p in shot_dir.iterdir()
                        if p.is_file() and p.suffix.lower() in image_exts
                    ),
                    key=lambda p: p.stat().st_mtime,
                    default=None,
                )

            if latest_path is not None:
                try:
                    st = latest_path.stat()
                    latest_name = latest_path.name
                    latest_kb = st.st_size / 1024.0
                    latest_dt = datetime.fromtimestamp(st.st_mtime)
                    age = datetime.now() - latest_dt
                    age_seconds = int(max(0, age.total_seconds()))
                    if age_seconds < 60:
                        latest_age = f"{age_seconds}s ago"
                    elif age_seconds < 3600:
                        latest_age = f"{age_seconds // 60}m ago"
                    elif age_seconds < 86400:
                        latest_age = f"{age_seconds // 3600}h ago"
                    else:
                        latest_age = f"{age_seconds // 86400}d ago"
                    try:
                        with routes.Image.open(latest_path) as im:
                            w, h = im.size
                            latest_dims = f"{w}x{h}"
                            if st.st_size < 12 * 1024 or w < 700 or h < 350:
                                tiny_count += 1
                                latest_tiny = True
                                issues.append("latest screenshot is tiny/low-detail")
                    except Exception:
                        latest_dims = "unknown"
                        issues.append("latest screenshot unreadable")
                except OSError:
                    issues.append("unable to stat latest screenshot")
            else:
                issues.append("no screenshots found")

            capture_failed = bool(template.get("capture_failed"))
            offline_since = (template.get("offline_since") or "").strip()
            if capture_failed:
                issues.append("capture_failed=1")
            if offline_since:
                issues.append(f"offline_since={offline_since}")

            if dedicated_xpath and latest_tiny:
                suggestions.append(
                    "Consider clearing dedicated_xpath (it may be cropping to a tiny element)."
                )
            if dedicated_xpath and any(
                "overly generic selector" in i
                for i in issues
                if isinstance(i, str) and i.startswith("dedicated_xpath:")
            ):
                suggestions.append(
                    "Make dedicated_xpath more specific (prefer @id, stable @class tokens, or constraints like contains(@src, ...))."
                )
            if popup_xpath and any(
                "overly generic selector" in i
                for i in issues
                if isinstance(i, str) and i.startswith("popup_xpath:")
            ):
                suggestions.append(
                    "Make popup_xpath more specific (prefer dialog container id/class and a close button selector)."
                )

            if issues:
                issue_count += 1

            rows.append(
                {
                    "name": name,
                    "popup_xpath": popup_xpath,
                    "dedicated_xpath": dedicated_xpath,
                    "issues": issues,
                    "suggestions": suggestions,
                    "latest_tiny": latest_tiny,
                    "capture_failed": capture_failed,
                    "offline_since": offline_since,
                    "latest_name": latest_name,
                    "latest_age": latest_age,
                    "latest_dims": latest_dims,
                    "latest_kb": latest_kb,
                }
            )

        rows.sort(key=lambda r: (-len(r["issues"]), r["name"]))
        summary = {
            "total": len(rows),
            "with_xpath": sum(
                1 for r in rows if r["popup_xpath"] or r["dedicated_xpath"]
            ),
            "issue_rows": issue_count,
            "tiny_rows": tiny_count,
        }

        return render_template(
            "xpath_health.html",
            rows=rows,
            summary=summary,
            page_title="XPath Health",
        )

    @bp.route("/xpath_health/clear", methods=["POST"], endpoint="xpath_health_clear")
    @routes.login_required
    def xpath_health_clear():
        """Clear an XPath field (popup/dedicated) for a template."""

        template_name = routes.validate_template_name(
            str(request.form.get("name") or "")
        )
        field = str(request.form.get("field") or "").strip()
        if template_name is None:
            routes.abort(404)
        if field not in {"popup_xpath", "dedicated_xpath"}:
            routes.abort(400)
        routes.template_manager.save_template(template_name, {field: ""})
        routes.flash(f"Cleared {field} for {template_name}", "success")
        return redirect(url_for("ui.xpath_health"))

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
        "/templates/<string:template_name>/event_buffer/test",
        methods=["POST"],
        endpoint="event_buffer_test",
    )
    @routes.login_required
    def event_buffer_test(template_name: routes.TemplateName):
        """Dry-run LAN event-buffer eligibility for a template form."""

        template_name = routes.validate_template_name(str(template_name))
        if template_name is None:
            routes.abort(404)
        template = routes.template_manager.get_template(template_name)
        if not template:
            routes.abort(404)

        payload = dict(template)
        payload.update(request.form.to_dict())
        if "event_buffer_enabled" not in request.form:
            payload["event_buffer_enabled"] = "false"
        try:
            sanitized = routes.validate_update_data(payload)
        except ValueError as exc:
            return jsonify({"ok": False, "status": "blocked", "message": str(exc)}), 400

        eligible, reason = routes.validators.event_buffer_eligibility(sanitized)
        if not eligible:
            return jsonify({"ok": False, "status": "blocked", "message": reason}), 400

        return jsonify(
            {
                "ok": True,
                "status": "ok",
                "message": (
                    f"{sanitized['event_buffer_fps']} fps, "
                    f"{sanitized['event_buffer_pre_seconds']}s pre, "
                    f"{sanitized['event_buffer_post_seconds']}s post, "
                    f"{sanitized['event_buffer_seconds']}s ring, "
                    f"{sanitized['event_buffer_backoff_seconds']}s backoff"
                ),
            }
        )

    @bp.route(
        "/templates/<string:template_name>/event_buffer/status",
        methods=["GET"],
        endpoint="event_buffer_status",
    )
    @routes.login_required
    def event_buffer_status(template_name: routes.TemplateName):
        """Return live LAN event-buffer status for a template."""

        template_name = routes.validate_template_name(str(template_name))
        if template_name is None:
            routes.abort(404)
        template = routes.template_manager.get_template(template_name)
        if not template:
            routes.abort(404)

        status = routes.event_buffer.event_buffer_status(template_name)
        return jsonify({"ok": True, "status": "ok", **status})

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
        target_name = template_name
        submitted_name = request.form.get("name")
        if submitted_name is not None:
            try:
                submitted_name = routes.validate_template_name(str(submitted_name))
            except Exception:
                submitted_name = None
            if submitted_name is None:
                if request.is_json:
                    return jsonify({"error": "Invalid template name"}), 400
                routes.flash("Invalid template name", "error")
                return redirect("/templates/" + template_name)
            if submitted_name != template_name:
                try:
                    target_name = routes.template_manager.rename_template(
                        template_name, submitted_name
                    )
                except ValueError as exc:
                    if request.is_json:
                        return jsonify({"error": str(exc)}), 400
                    routes.flash(str(exc), "error")
                    return redirect("/templates/" + template_name)
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
            "stabilize_mode": request.form.get("stabilize_mode"),
            "capture_rotate_degrees": request.form.get("capture_rotate_degrees"),
            "night_enhance_mode": request.form.get("night_enhance_mode"),
            "deflicker_mode": request.form.get("deflicker_mode"),
            "source_template": request.form.get("source_template"),
            "burst_enhance_mode": request.form.get("burst_enhance_mode"),
            "burst_enhance_profile": request.form.get("burst_enhance_profile"),
            "burst_enhance_roi": request.form.get("burst_enhance_roi"),
            "capture_crop_roi": request.form.get("capture_crop_roi"),
            "lens_correction_spec": request.form.get("lens_correction_spec"),
            "horizon_level_mode": request.form.get("horizon_level_mode"),
            "horizon_level_roi": request.form.get("horizon_level_roi"),
            "composite_view_mode": request.form.get("composite_view_mode"),
            "composite_view_spec": request.form.get("composite_view_spec"),
            "event_buffer_enabled": request.form.get("event_buffer_enabled", "false"),
            "event_buffer_profile": request.form.get("event_buffer_profile"),
            "event_buffer_fps": request.form.get("event_buffer_fps"),
            "event_buffer_seconds": request.form.get("event_buffer_seconds"),
            "event_buffer_width": request.form.get("event_buffer_width"),
            "event_buffer_pre_seconds": request.form.get("event_buffer_pre_seconds"),
            "event_buffer_post_seconds": request.form.get("event_buffer_post_seconds"),
            "event_buffer_format": request.form.get("event_buffer_format"),
            "event_buffer_backoff_seconds": request.form.get(
                "event_buffer_backoff_seconds"
            ),
            "disable_autocrop": request.form.get("disable_autocrop", "false").lower()
            in ["true", "1", "t", "y", "yes", "on"],
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
                onvif_updates = _probe_onvif_metadata(
                    url,
                    username=updated_data.get("auth_username") or None,
                    password=updated_data.get("auth_password") or None,
                    replace_url=True,
                )
            except Exception as exc:  # pragma: no cover - network issues
                logging.error("ONVIF autodetect failed for %s: %s", url, exc)
                onvif_updates = {}
        else:
            onvif_updates = {}

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
        updated_data.update(onvif_updates)
        routes.template_manager.save_template(target_name, updated_data)
        for job_name in {template_name, target_name}:
            try:
                routes.scheduling.scheduler.remove_job(job_name)
            except LookupError:
                pass
        routes.screenshots.create_blank_frame(target_name)
        updated_data = routes.template_manager.get_template(target_name) or updated_data
        try:
            seconds = 60 * max(1, int(updated_data.get("frequency") or 30))
            routes.scheduling.scheduler.add_job(
                func=routes.scheduling.update_camera,
                trigger="interval",
                seconds=seconds,
                args=[target_name, updated_data],
                id=target_name,
                executor=routes.scheduling.camera_executor(updated_data),
                max_instances=1,
                coalesce=True,
                replace_existing=True,
            )
        except Exception as e:  # pragma: no cover - scheduler failure
            logging.error("job schedule error: %s", e)
        if request.is_json:
            return jsonify({"message": "Template updated successfully!"})
        return redirect("/templates/" + target_name)

    @bp.route(
        "/templates/<string:template_name>/ptz/refresh",
        methods=["POST"],
        endpoint="refresh_template_ptz",
    )
    @routes.login_required
    def refresh_template_ptz(template_name: routes.TemplateName):
        """Probe and persist ONVIF PTZ metadata for ``template_name``."""

        template_name = routes.validate_template_name(str(template_name))
        if template_name is None:
            routes.abort(404)
        template = routes.template_manager.get_template(template_name)
        if not template:
            routes.abort(404)

        updates = _probe_onvif_metadata(
            str(template.get("url") or ""),
            username=template.get("auth_username") or None,
            password=template.get("auth_password") or None,
            replace_url=False,
            existing=template,
        )
        routes.template_manager.save_template(template_name, updates)
        refreshed = routes.template_manager.get_template(template_name)
        return jsonify(
            {
                "ok": bool(refreshed and refreshed.get("ptz_enabled")),
                "ptz": _ptz_state_from_template(refreshed),
            }
        )

    @bp.route(
        "/templates/<string:template_name>/ptz",
        methods=["POST"],
        endpoint="control_template_ptz",
    )
    @routes.login_required
    def control_template_ptz(template_name: routes.TemplateName):
        """Execute a PTZ action for ``template_name`` using PTZ controls."""

        template_name = routes.validate_template_name(str(template_name))
        if template_name is None:
            routes.abort(404)
        template = routes.template_manager.get_template(template_name)
        if not template:
            routes.abort(404)

        payload = request.get_json(silent=True) or {}
        action = str(payload.get("action") or "").strip().lower()
        if action not in {"move", "stop", "preset"}:
            return jsonify({"ok": False, "error": "invalid_action"}), 400

        ptz_kwargs: dict[str, object] = {
            "action": action,
            "username": template.get("auth_username") or None,
            "password": template.get("auth_password") or None,
            "profile_token": template.get("ptz_profile_token") or None,
            "ptz_service": template.get("ptz_service") or None,
        }
        if action == "move":
            direction = str(payload.get("direction") or "").strip().lower()
            if (
                direction not in _PTZ_DIRECTION_VECTORS
                and direction not in _PTZ_LENS_DIRECTIONS
            ):
                return jsonify({"ok": False, "error": "invalid_direction"}), 400
            try:
                speed = float(template.get("ptz_speed") or 0.6)
            except (TypeError, ValueError):
                speed = 0.6
            speed = max(0.1, min(speed, 1.0))
            try:
                default_duration_ms = int(template.get("ptz_duration_ms") or 450)
            except (TypeError, ValueError):
                default_duration_ms = 450
            default_duration_ms = max(100, min(default_duration_ms, 10000))
            ptz_kwargs.update(
                {
                    "direction": direction,
                    "vendor_driver": template.get("ptz_vendor_driver") or None,
                    "duration_ms": payload.get("duration_ms", default_duration_ms),
                }
            )
            if direction in _PTZ_DIRECTION_VECTORS:
                pan, tilt, zoom = _PTZ_DIRECTION_VECTORS[direction]
                ptz_kwargs.update(
                    {
                        "pan": pan * speed,
                        "tilt": tilt * speed,
                        "zoom": zoom * speed,
                    }
                )
        elif action == "preset":
            preset_token = str(payload.get("preset_token") or "").strip()
            if not preset_token:
                return jsonify({"ok": False, "error": "missing_preset"}), 400
            ptz_kwargs["preset_token"] = preset_token

        from app.utils import ptz_views

        try:
            with ptz_views.manual(template_name):
                result = routes.camera_discovery.control_ptz(
                    str(template.get("url") or ""), **ptz_kwargs
                )
        except ptz_views.Busy:
            return jsonify({"ok": False, "error": "ptz_busy_retry"}), 409
        metadata = result.get("metadata") if isinstance(result, dict) else None
        if isinstance(metadata, dict):
            routes.template_manager.save_template(
                template_name, _build_ptz_template_updates(metadata, existing=template)
            )
        refreshed = routes.template_manager.get_template(template_name)
        body = {
            "ok": bool(result.get("ok")),
            "ptz": _ptz_state_from_template(refreshed),
        }
        if result.get("error"):
            body["error"] = result["error"]
        return jsonify(body), 200 if body["ok"] else 400

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

    # --- Integrations -------------------------------------------------------

    @bp.route("/integrations/google", endpoint="google_home")
    @routes.login_required
    def google_home():
        """Google Home / Nest camera integration status page."""

        from app.utils import google_sdm
        from app.utils.google_sdm_profiles import list_profile_names

        profile_names = list_profile_names()
        profiles = ["default", *[p for p in profile_names if p != "default"]]

        selected = (request.args.get("profile") or "").strip() or "default"
        if selected not in profiles:
            selected = "default"

        # For the UI, show the stored values even if a profile isn't fully
        # configured yet (so users can see/edit what they've already entered).
        raw = routes.config.get_setting("GOOGLE_SDM_PROFILES", "") or ""
        try:
            payload = routes.json.loads(raw) if str(raw).strip() else {}
        except Exception:
            payload = {}
        if not isinstance(payload, dict):
            payload = {}

        stored = payload.get(selected)
        if not isinstance(stored, dict):
            stored = {}

        project_id = str(stored.get("project_id") or "").strip()
        client_id = str(stored.get("client_id") or "").strip()
        redirect_uri = str(stored.get("redirect_uri") or "").strip()
        client_secret_saved = bool(str(stored.get("client_secret") or "").strip())
        refresh_token_saved = bool(str(stored.get("refresh_token") or "").strip())

        # Legacy single-project settings (only meaningful for the default profile).
        if selected == "default":
            legacy_project_id = str(
                routes.config.get_setting("GOOGLE_SDM_PROJECT_ID", "") or ""
            ).strip()
            legacy_client_id = str(
                routes.config.get_setting("GOOGLE_SDM_CLIENT_ID", "") or ""
            ).strip()
            legacy_client_secret = str(
                routes.config.get_setting("GOOGLE_SDM_CLIENT_SECRET", "") or ""
            ).strip()
            legacy_redirect_uri = str(
                routes.config.get_setting("GOOGLE_SDM_REDIRECT_URI", "") or ""
            ).strip()
            legacy_refresh_token = str(
                routes.config.get_setting("GOOGLE_SDM_REFRESH_TOKEN", "") or ""
            ).strip()

            project_id = project_id or legacy_project_id
            client_id = client_id or legacy_client_id
            redirect_uri = redirect_uri or legacy_redirect_uri
            client_secret_saved = client_secret_saved or bool(legacy_client_secret)
            refresh_token_saved = refresh_token_saved or bool(legacy_refresh_token)

        configured = bool(google_sdm.configured(selected))
        connected = refresh_token_saved

        return render_template(
            "google_home.html",
            configured=configured,
            connected=connected,
            profiles=profiles,
            selected_profile=selected,
            project_id=project_id,
            redirect_uri=redirect_uri,
            client_id=client_id,
            client_secret_saved=client_secret_saved,
            page_title="Google Home",
        )

    @bp.route(
        "/integrations/google/profile",
        methods=["POST"],
        endpoint="google_home_profile",
    )
    @routes.login_required
    def google_home_profile():
        """Create/update a Google SDM profile in GOOGLE_SDM_PROFILES."""

        profile = (request.form.get("profile") or "").strip().lower()
        if not profile:
            routes.flash("Profile name is required.", "error")
            return redirect(url_for("ui.google_home"))

        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,31}", profile):
            routes.flash(
                "Invalid profile name. Use 1-32 chars: a-z, 0-9, '_' or '-'.",
                "error",
            )
            return redirect(url_for("ui.google_home"))

        project_id = (request.form.get("project_id") or "").strip()
        client_id = (request.form.get("client_id") or "").strip()
        client_secret = (request.form.get("client_secret") or "").strip()
        redirect_uri = (request.form.get("redirect_uri") or "").strip()

        raw = routes.config.get_setting("GOOGLE_SDM_PROFILES", "") or ""
        try:
            payload = routes.json.loads(raw) if str(raw).strip() else {}
        except Exception:
            payload = {}
        if not isinstance(payload, dict):
            payload = {}

        existing = payload.get(profile)
        if not isinstance(existing, dict):
            existing = {}

        # Preserve secrets/tokens unless explicitly replaced.
        if not client_secret:
            client_secret = str(existing.get("client_secret") or "").strip()
        refresh_token = str(existing.get("refresh_token") or "").strip()

        payload[profile] = {
            "project_id": project_id,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "refresh_token": refresh_token,
        }

        routes.update_setting(
            "GOOGLE_SDM_PROFILES", routes.json.dumps(payload), restart=False
        )
        routes.flash(f"Saved Google SDM profile '{profile}'.", "success")
        return redirect(url_for("ui.google_home", profile=profile))

    @bp.route("/integrations/google/connect", endpoint="google_home_connect")
    @routes.login_required
    def google_home_connect():
        """Start OAuth flow for Google SDM."""

        import secrets

        from app.utils import google_sdm

        profile = (request.args.get("profile") or "").strip() or "default"
        if not google_sdm.configured(profile):
            routes.flash(
                f"Google SDM profile '{profile}' is not configured yet.",
                "error",
            )
            return redirect(url_for("ui.google_home", profile=profile))

        state = secrets.token_urlsafe(24)
        _store_google_oauth_state(state, profile)
        return redirect(google_sdm.build_oauth_authorize_url(state, profile))

    @bp.route("/integrations/google/callback", endpoint="google_home_callback")
    @routes.login_required
    def google_home_callback():
        """OAuth callback endpoint for Google SDM."""

        from app.utils import google_sdm

        code = (request.args.get("code") or "").strip()
        state = (request.args.get("state") or "").strip()

        if not code:
            routes.flash("Google OAuth callback missing code", "error")
            return redirect(url_for("ui.google_home"))

        profile = _pop_google_oauth_profile(state)
        if not profile:
            routes.flash("Google OAuth state mismatch; please try again", "error")
            return redirect(url_for("ui.google_home"))

        try:
            refresh, access, expires_in = google_sdm.exchange_code_for_refresh_token(
                code, profile
            )
        except Exception as exc:
            routes.flash(f"Google OAuth failed: {exc}", "error")
            return redirect(url_for("ui.google_home", profile=profile))

        # Persist refresh token (no restart required).
        raw_profiles = routes.config.get_setting("GOOGLE_SDM_PROFILES", "") or ""
        try:
            payload = (
                routes.json.loads(raw_profiles) if str(raw_profiles).strip() else {}
            )
        except Exception:
            payload = {}
        if not isinstance(payload, dict):
            payload = {}

        prof_data = payload.get(profile)
        if not isinstance(prof_data, dict):
            prof_data = {}
        prof_data["refresh_token"] = str(refresh)
        payload[profile] = prof_data

        routes.update_setting(
            "GOOGLE_SDM_PROFILES", routes.json.dumps(payload), restart=False
        )
        routes.update_setting(
            "GOOGLE_SDM_CONNECTED_AT",
            datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
            restart=False,
        )

        # Warm the in-process cache for immediate use.
        try:
            google_sdm.clear_cached_tokens()
            _ = access
            _ = expires_in
        except Exception:
            pass

        routes.flash("Google Home connected. You can now import cameras.", "success")
        return redirect(url_for("ui.google_home_devices", profile=profile))

    @bp.route(
        "/integrations/google/disconnect",
        methods=["POST"],
        endpoint="google_home_disconnect",
    )
    @routes.login_required
    def google_home_disconnect():
        """Disconnect Google SDM by removing stored refresh token."""

        from app.utils import google_sdm

        profile = (request.args.get("profile") or "").strip() or "default"
        raw_profiles = routes.config.get_setting("GOOGLE_SDM_PROFILES", "") or ""

        if str(raw_profiles).strip():
            try:
                payload = routes.json.loads(raw_profiles)
            except Exception:
                payload = {}
            if isinstance(payload, dict) and isinstance(payload.get(profile), dict):
                payload[profile]["refresh_token"] = ""
                routes.update_setting(
                    "GOOGLE_SDM_PROFILES", routes.json.dumps(payload), restart=False
                )
        else:
            routes.update_setting("GOOGLE_SDM_REFRESH_TOKEN", "", restart=False)

        google_sdm.clear_cached_tokens()
        routes.flash("Google Home disconnected.", "success")
        return redirect(url_for("ui.google_home", profile=profile))

    @bp.route("/kiosk_live_config")
    @routes.login_required
    def kiosk_live_config():
        """Issue a scoped, short-lived Google session token for verified views."""
        from app.utils import google_sdm

        camera = request.args.get("camera", "")
        if camera not in VIEWER_CONFIG.get("google_live_cameras", []):
            abort(404)
        details = routes.template_manager.get_template(camera) or {}
        if details.get("private_camera"):
            abort(403)
        profile, device_id = google_sdm.parse_sdm_url(details.get("url", ""))
        if not device_id:
            abort(404)
        profile = profile or "default"
        response = jsonify(
            {
                "profile": profile,
                "device_id": device_id,
                "token": google_sdm.issue_webrtc_preview_token(profile, device_id),
            }
        )
        response.headers["Cache-Control"] = "no-store"
        return response

    def _google_webrtc_request_args() -> tuple[str, str, str]:
        """Return normalized `(profile, device_id, token)` from request params/body."""

        payload = request.get_json(silent=True) or {}
        profile = (
            str(payload.get("profile") or request.values.get("profile") or "").strip()
            or "default"
        )
        device_id = str(
            payload.get("device_id") or request.values.get("device_id") or ""
        ).strip()
        token = str(payload.get("token") or request.values.get("token") or "").strip()
        return profile, device_id, token

    def _google_webrtc_authorized(profile: str, device_id: str, token: str) -> bool:
        """Allow either logged-in user or valid signed preview token."""

        if bool(getattr(current_user, "is_authenticated", False)):
            return True
        from app.utils import google_sdm

        verified = google_sdm.verify_webrtc_preview_token(token, max_age_seconds=900)
        if not verified:
            return False
        vp, vd = verified
        return vp == profile and vd == device_id

    def _normalize_webrtc_offer_sdp(raw_offer: str) -> str:
        """Normalize SDP to strict CRLF line endings expected by SDM.

        Some clients can accidentally pass escaped line breaks (`\\r\\n`) or mixed
        endings. SDM rejects those payloads with INVALID_ARGUMENT.
        """

        offer_sdp = str(raw_offer or "")
        if not offer_sdp.strip():
            return ""

        # If the client accidentally sent JSON-escaped text, decode it back.
        if "\\r\\n" in offer_sdp and "\r\n" not in offer_sdp and "\n" not in offer_sdp:
            offer_sdp = offer_sdp.replace("\\r\\n", "\r\n").replace("\\n", "\n")

        normalized = offer_sdp.replace("\r\n", "\n").replace("\r", "\n")
        lines = [line for line in normalized.split("\n") if line != ""]
        if not lines:
            return ""
        return "\r\n".join(lines) + "\r\n"

    @bp.route(
        "/integrations/google/webrtc/preview",
        methods=["GET"],
        endpoint="google_webrtc_preview",
    )
    def google_webrtc_preview():
        """Minimal WebRTC preview page used for SDM WEB_RTC captures/live view."""

        profile, device_id, token = _google_webrtc_request_args()
        if not device_id:
            abort(400, "device_id required")
        if not _google_webrtc_authorized(profile, device_id, token):
            abort(403)

        return render_template(
            "google_home_webrtc_preview.html",
            profile=profile,
            device_id=device_id,
            token=token,
            page_title=f"Google Camera {device_id[:8]}",
        )

    @bp.route(
        "/integrations/google/webrtc/start",
        methods=["POST"],
        endpoint="google_webrtc_start",
    )
    def google_webrtc_start():
        """Accept browser SDP offer and return SDM WebRTC answer."""

        from app.utils import google_sdm

        profile, device_id, token = _google_webrtc_request_args()
        if not device_id:
            return jsonify({"ok": False, "error": "device_id required"}), 400
        if not _google_webrtc_authorized(profile, device_id, token):
            return jsonify({"ok": False, "error": "unauthorized"}), 403

        payload = request.get_json(silent=True) or {}
        offer_sdp = _normalize_webrtc_offer_sdp(payload.get("offer_sdp") or "")
        if not offer_sdp:
            return jsonify({"ok": False, "error": "offer_sdp required"}), 400
        offer_lines = [line for line in offer_sdp.split("\r\n") if line]
        logging.info(
            (
                "google_webrtc_start offer profile=%s device=%s lines=%d "
                "ends_crlf=%s has_bare_lf=%s"
            ),
            profile,
            device_id[:12] + "…" if len(device_id) > 12 else device_id,
            max(len(offer_lines), 0),
            offer_sdp.endswith("\r\n"),
            ("\n" in offer_sdp.replace("\r\n", "")),
        )

        try:
            _p, device_name = google_sdm.webrtc_device_name_from_stable_url(
                f"sdm://{profile}/{device_id}"
            )
            stream = google_sdm.generate_webrtc_stream(device_name, offer_sdp, profile)
        except Exception as exc:
            logging.warning(
                "google_webrtc_start failed profile=%s device=%s: %s",
                profile,
                device_id,
                exc,
            )
            return jsonify({"ok": False, "error": str(exc)}), 502

        logging.info(
            "google_webrtc_start ok profile=%s device=%s media_session=%s answer_len=%s",
            profile,
            device_id[:12] + "…" if len(device_id) > 12 else device_id,
            (
                stream.media_session_id[:12] + "…"
                if len(stream.media_session_id) > 12
                else stream.media_session_id
            ),
            len(stream.answer_sdp or ""),
        )
        return jsonify(
            {
                "ok": True,
                "answer_sdp": stream.answer_sdp,
                "media_session_id": stream.media_session_id,
                "expires_at": (
                    stream.expires_at.isoformat() if stream.expires_at else None
                ),
            }
        )

    @bp.route(
        "/integrations/google/webrtc/extend",
        methods=["POST"],
        endpoint="google_webrtc_extend",
    )
    def google_webrtc_extend():
        """Extend an active SDM WebRTC session."""

        from app.utils import google_sdm

        profile, device_id, token = _google_webrtc_request_args()
        if not device_id:
            return jsonify({"ok": False, "error": "device_id required"}), 400
        if not _google_webrtc_authorized(profile, device_id, token):
            return jsonify({"ok": False, "error": "unauthorized"}), 403

        payload = request.get_json(silent=True) or {}
        media_session_id = str(payload.get("media_session_id") or "").strip()
        if not media_session_id:
            return jsonify({"ok": False, "error": "media_session_id required"}), 400

        try:
            _p, device_name = google_sdm.webrtc_device_name_from_stable_url(
                f"sdm://{profile}/{device_id}"
            )
            expires_at = google_sdm.extend_webrtc_stream(
                device_name, media_session_id, profile
            )
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 502

        return jsonify(
            {
                "ok": True,
                "expires_at": expires_at.isoformat() if expires_at else None,
            }
        )

    @bp.route(
        "/integrations/google/webrtc/stop",
        methods=["POST"],
        endpoint="google_webrtc_stop",
    )
    def google_webrtc_stop():
        """Stop an active SDM WebRTC session."""

        from app.utils import google_sdm

        profile, device_id, token = _google_webrtc_request_args()
        if not device_id:
            return jsonify({"ok": False, "error": "device_id required"}), 400
        if not _google_webrtc_authorized(profile, device_id, token):
            return jsonify({"ok": False, "error": "unauthorized"}), 403

        payload = request.get_json(silent=True) or {}
        media_session_id = str(payload.get("media_session_id") or "").strip()
        if not media_session_id:
            return jsonify({"ok": False, "error": "media_session_id required"}), 400

        try:
            _p, device_name = google_sdm.webrtc_device_name_from_stable_url(
                f"sdm://{profile}/{device_id}"
            )
            google_sdm.stop_webrtc_stream(device_name, media_session_id, profile)
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 502

        return jsonify({"ok": True})

    def _sdm_device_id(device: dict) -> str | None:
        name = str(device.get("name") or "")
        if "/devices/" not in name:
            return None
        return name.split("/devices/", 1)[-1].strip() or None

    def _sdm_device_label(device: dict) -> str:
        traits = device.get("traits") or {}
        info = traits.get("sdm.devices.traits.Info") or {}
        custom = str(info.get("customName") or "").strip()
        if custom:
            return custom

        rel = device.get("parentRelations") or []
        for item in rel:
            if not isinstance(item, dict):
                continue
            dn = str(item.get("displayName") or "").strip()
            if dn:
                return dn

        return str(device.get("type") or "Camera").split(".")[-1] or "Camera"

    def _sdm_structure_room(device: dict) -> tuple[str, str]:
        struct = ""
        room = ""
        rel = device.get("parentRelations") or []
        for item in rel:
            if not isinstance(item, dict):
                continue
            rtype = str(item.get("relationType") or "").strip().upper()
            dn = str(item.get("displayName") or "").strip()
            if rtype == "STRUCTURE" and dn:
                struct = dn
            elif rtype == "ROOM" and dn:
                room = dn
        return struct, room

    def _make_template_name(base: str, existing: set[str]) -> str:
        # Allowed: letters/digits/_-. and max len 32.
        cleaned: list[str] = []
        for ch in base:
            if ch.isalnum() or ch in "_-.":
                cleaned.append(ch)
            elif ch.isspace():
                cleaned.append("_")
        name = "".join(cleaned).strip("-_ .")
        name = name.replace("__", "_").replace("--", "-")
        if not name:
            name = "GoogleCam"

        name = name[:32]
        if name in existing:
            stem = name
            i = 2
            while True:
                suffix = f"-{i}"
                candidate = (stem[: 32 - len(suffix)] + suffix).rstrip("-_ .")
                if candidate and candidate not in existing:
                    name = candidate
                    break
                i += 1
        existing.add(name)
        return name

    @bp.route(
        "/integrations/google/devices",
        methods=["GET", "POST"],
        endpoint="google_home_devices",
    )
    @routes.login_required
    def google_home_devices():
        """List Google SDM devices and import cameras."""

        from app.utils import google_sdm
        from app.utils.google_sdm_profiles import resolve_profile

        profile = (request.args.get("profile") or "").strip() or "default"
        list_error = ""
        # Default new imports into the selected household profile group
        # when possible, so they appear in the expected video wall immediately.
        default_group = validate_group_name(profile) or "google_home"

        if request.method == "POST":
            device_ids = request.form.getlist("device_id")
            group = (
                request.form.get("group") or default_group
            ).strip() or default_group
            frequency = int(request.form.get("frequency") or 2)
            logging.info(
                "google_sdm import profile=%s selected=%s group=%s frequency=%s ip=%s",
                profile,
                len(device_ids),
                group,
                frequency,
                request.remote_addr,
            )

            templates = routes.template_manager.get_templates()
            existing_names = set(templates.keys())

            imported = 0
            for did in device_ids:
                did = str(did).strip()
                if not did:
                    continue

                label = (request.form.get(f"label_{did}") or "GoogleCam").strip()
                tname = _make_template_name(label, existing_names)
                ok = routes.template_manager.save_template(
                    tname,
                    {
                        "url": f"sdm://{profile}/{did}",
                        "groups": group,
                        "frequency": frequency,
                        "headless": False,
                        "browser": False,
                        "stealth": False,
                        "dark": True,
                    },
                )
                if ok:
                    imported += 1
                else:
                    # Avoid dumping full IDs into the log; they're long.
                    did_short = did[:12] + "…" + did[-6:] if len(did) > 24 else did
                    logging.warning(
                        "google_sdm import failed profile=%s name=%s device_id=%s",
                        profile,
                        tname,
                        did_short,
                    )

            if imported:
                routes.flash(f"Imported {imported} Google Home camera(s).", "success")
                primary_group = (group.split(",")[0] or "").strip()
                if primary_group:
                    return redirect(
                        routes.url_for("views.group_page", group_name=primary_group)
                    )
            else:
                routes.flash("No cameras imported.", "info")
            return redirect(url_for("ui.google_home_devices", profile=profile))

        if not google_sdm.configured(profile):
            routes.flash(
                f"Google SDM profile '{profile}' is not configured yet.", "error"
            )
            return redirect(url_for("ui.google_home", profile=profile))

        prof = resolve_profile(profile)
        if not (prof and prof.refresh_token):
            routes.flash(
                f"Google SDM profile '{profile}' is not connected yet.", "error"
            )
            return redirect(url_for("ui.google_home", profile=profile))

        try:
            devices = google_sdm.list_devices(profile)
        except Exception as exc:
            list_error = str(exc)
            routes.flash(f"Failed to list Google devices: {list_error}", "error")
            devices = []

        camera_rows: list[dict[str, object]] = []
        for dev in devices:
            did = _sdm_device_id(dev)
            if not did:
                continue

            traits = dev.get("traits") or {}
            stream_trait = traits.get("sdm.devices.traits.CameraLiveStream") or {}
            supported_protocols = [
                str(p).upper() for p in (stream_trait.get("supportedProtocols") or [])
            ]
            device_type = str(dev.get("type") or "")
            is_camera_type = device_type.upper().endswith((".CAMERA", ".DOORBELL"))
            has_stream = bool(stream_trait)
            supports_rtsp = "RTSP" in supported_protocols
            supports_webrtc = "WEB_RTC" in supported_protocols
            has_rtsp = supports_rtsp and is_camera_type
            importable = bool(
                is_camera_type and has_stream and (has_rtsp or supports_webrtc)
            )
            struct, room = _sdm_structure_room(dev)
            camera_rows.append(
                {
                    "device_id": did,
                    "label": _sdm_device_label(dev),
                    "type": device_type,
                    "is_camera_type": bool(is_camera_type),
                    "has_stream": bool(has_stream),
                    "has_rtsp": bool(has_rtsp),
                    "supports_rtsp": bool(supports_rtsp),
                    "supports_webrtc": bool(supports_webrtc),
                    "importable": importable,
                    "protocols": supported_protocols,
                    "structure": struct,
                    "room": room,
                }
            )

        camera_rows.sort(key=lambda r: (not r["has_stream"], str(r["label"]).lower()))

        return render_template(
            "google_home_devices.html",
            cameras=camera_rows,
            list_error=list_error,
            profile=profile,
            default_group=default_group,
            page_title="Google Home Cameras",
        )

    @bp.route("/integrations/eufy", endpoint="eufy_home")
    @routes.login_required
    def eufy_home():
        """Eufy cloud bridge profile management page."""

        from app.utils import eufy_cloud

        def _resolve_profile_or_fallback(raw_name: str) -> str:
            requested = str(raw_name or "").strip().lower() or "default"
            names = eufy_cloud.list_profile_names()
            if requested not in names:
                requested = "default"
            if requested != "default":
                return requested
            if eufy_cloud.configured("default"):
                return "default"
            for candidate in names:
                if candidate == "default":
                    continue
                if eufy_cloud.configured(candidate):
                    return candidate
            return requested

        profile_names = eufy_cloud.list_profile_names()
        selected = _resolve_profile_or_fallback(request.args.get("profile"))

        raw = routes.config.get_setting("EUFY_CLOUD_PROFILES", "") or ""
        try:
            payload = routes.json.loads(raw) if str(raw).strip() else {}
        except Exception:
            payload = {}
        if not isinstance(payload, dict):
            payload = {}

        stored = payload.get(selected)
        if not isinstance(stored, dict):
            stored = {}

        mode = str(stored.get("mode") or "external").strip().lower()
        if mode not in {"emulator", "external"}:
            mode = "external"
        bridge_url = str(stored.get("bridge_url") or "").strip()
        api_token = str(stored.get("api_token") or "").strip()
        devices_path = str(stored.get("devices_path") or "/api/devices").strip()
        snapshot_path = str(
            stored.get("snapshot_path") or "/api/cameras/{device_id}/snapshot"
        ).strip()
        verify_tls = str(stored.get("verify_tls", "true")).strip().lower() in {
            "true",
            "1",
            "yes",
            "on",
            "y",
            "t",
        }
        emulator_adb_path = str(stored.get("emulator_adb_path") or "").strip()
        emulator_adb_serial = str(stored.get("emulator_adb_serial") or "").strip()
        emulator_launch_cmd = str(stored.get("emulator_launch_cmd") or "").strip()
        emulator_capture_cmd = str(stored.get("emulator_capture_cmd") or "").strip()
        emulator_boot_cmd = str(stored.get("emulator_boot_cmd") or "").strip()
        emulator_devices_json = str(stored.get("emulator_devices_json") or "").strip()
        try:
            emulator_boot_timeout_seconds = float(
                stored.get("emulator_boot_timeout_seconds") or 45.0
            )
        except Exception:
            emulator_boot_timeout_seconds = 45.0
        emulator_boot_timeout_seconds = max(
            5.0, min(emulator_boot_timeout_seconds, 240.0)
        )
        try:
            emulator_settle_seconds = float(
                stored.get("emulator_settle_seconds") or 2.0
            )
        except Exception:
            emulator_settle_seconds = 2.0
        emulator_settle_seconds = max(0.0, min(emulator_settle_seconds, 60.0))
        configured = bool(eufy_cloud.configured(selected))
        requested_group = (request.args.get("group") or "").strip()
        suggested_group = (
            validate_group_name(requested_group)
            or validate_group_name("" if selected == "default" else selected)
            or "eufy"
        )

        return render_template(
            "eufy_home.html",
            profiles=profile_names,
            selected_profile=selected,
            configured=configured,
            mode=mode,
            bridge_url=bridge_url,
            api_token=api_token,
            devices_path=devices_path,
            snapshot_path=snapshot_path,
            verify_tls=verify_tls,
            emulator_adb_path=emulator_adb_path,
            emulator_adb_serial=emulator_adb_serial,
            emulator_launch_cmd=emulator_launch_cmd,
            emulator_capture_cmd=emulator_capture_cmd,
            emulator_boot_cmd=emulator_boot_cmd,
            emulator_boot_timeout_seconds=emulator_boot_timeout_seconds,
            emulator_devices_json=emulator_devices_json,
            emulator_settle_seconds=emulator_settle_seconds,
            suggested_group=suggested_group,
            page_title="Eufy Integration",
        )

    @bp.route(
        "/integrations/eufy/profile",
        methods=["POST"],
        endpoint="eufy_profile",
    )
    @routes.login_required
    def eufy_profile():
        """Create or update an Eufy cloud bridge profile."""

        profile = (request.form.get("profile") or "").strip().lower()
        if not profile:
            routes.flash("Profile name is required.", "error")
            return redirect(url_for("ui.eufy_home"))

        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,31}", profile):
            routes.flash(
                "Invalid profile name. Use 1-32 chars: a-z, 0-9, '_' or '-'.",
                "error",
            )
            return redirect(url_for("ui.eufy_home"))

        mode = (request.form.get("mode") or "").strip().lower() or "external"
        if mode not in {"emulator", "external"}:
            mode = "external"
        bridge_url = (request.form.get("bridge_url") or "").strip().rstrip("/")
        api_token = (request.form.get("api_token") or "").strip()
        devices_path = (
            request.form.get("devices_path") or ""
        ).strip() or "/api/devices"
        snapshot_path = (
            request.form.get("snapshot_path") or ""
        ).strip() or "/api/cameras/{device_id}/snapshot"
        verify_tls = str(request.form.get("verify_tls") or "").lower() in {
            "1",
            "true",
            "on",
            "yes",
        }
        emulator_adb_path = (request.form.get("emulator_adb_path") or "").strip()
        emulator_adb_serial = (request.form.get("emulator_adb_serial") or "").strip()
        emulator_launch_cmd = (request.form.get("emulator_launch_cmd") or "").strip()
        emulator_capture_cmd = (request.form.get("emulator_capture_cmd") or "").strip()
        emulator_boot_cmd = (request.form.get("emulator_boot_cmd") or "").strip()
        emulator_devices_json = (
            request.form.get("emulator_devices_json") or ""
        ).strip()
        try:
            emulator_boot_timeout_seconds = float(
                request.form.get("emulator_boot_timeout_seconds") or 45.0
            )
        except Exception:
            emulator_boot_timeout_seconds = 45.0
        emulator_boot_timeout_seconds = max(
            5.0, min(emulator_boot_timeout_seconds, 240.0)
        )
        try:
            emulator_settle_seconds = float(
                request.form.get("emulator_settle_seconds") or 2.0
            )
        except Exception:
            emulator_settle_seconds = 2.0
        emulator_settle_seconds = max(0.0, min(emulator_settle_seconds, 60.0))
        raw = routes.config.get_setting("EUFY_CLOUD_PROFILES", "") or ""
        try:
            payload = routes.json.loads(raw) if str(raw).strip() else {}
        except Exception:
            payload = {}
        if not isinstance(payload, dict):
            payload = {}

        existing = payload.get(profile)
        if not isinstance(existing, dict):
            existing = {}

        if mode == "external" and not bridge_url:
            routes.flash("Bridge URL is required for external bridge mode.", "error")
            return redirect(url_for("ui.eufy_home", profile=profile))

        payload[profile] = {
            "mode": mode,
            "bridge_url": bridge_url,
            "api_token": api_token,
            "devices_path": devices_path,
            "snapshot_path": snapshot_path,
            "verify_tls": verify_tls,
            "emulator_adb_path": emulator_adb_path,
            "emulator_adb_serial": emulator_adb_serial,
            "emulator_launch_cmd": emulator_launch_cmd,
            "emulator_capture_cmd": emulator_capture_cmd,
            "emulator_boot_cmd": emulator_boot_cmd,
            "emulator_boot_timeout_seconds": emulator_boot_timeout_seconds,
            "emulator_devices_json": emulator_devices_json,
            "emulator_settle_seconds": emulator_settle_seconds,
        }

        routes.update_setting(
            "EUFY_CLOUD_PROFILES", routes.json.dumps(payload), restart=False
        )
        routes.flash(f"Saved Eufy profile '{profile}'.", "success")
        return redirect(url_for("ui.eufy_home", profile=profile))

    @bp.route(
        "/integrations/eufy/captcha",
        methods=["POST"],
        endpoint="eufy_captcha",
    )
    @routes.login_required
    def eufy_captcha():
        """Disabled: native captcha flow stays off in bridge/emulator deployments."""
        profile = (request.form.get("profile") or "").strip().lower() or "default"
        routes.flash(
            "Eufy API/web captcha flow is disabled. Use the external bridge or VM / Emulator integration.",
            "info",
        )
        return redirect(url_for("ui.eufy_home", profile=profile))

    @bp.route(
        "/integrations/eufy/captcha/auto",
        methods=["POST"],
        endpoint="eufy_captcha_auto",
    )
    @routes.login_required
    def eufy_captcha_auto():
        """Disabled: native captcha flow stays off in bridge/emulator deployments."""
        profile = (request.form.get("profile") or "").strip().lower() or "default"
        routes.flash(
            "Eufy API/web captcha flow is disabled. Use the external bridge or VM / Emulator integration.",
            "info",
        )
        return redirect(url_for("ui.eufy_home", profile=profile))

    @bp.route(
        "/integrations/eufy/captcha/request",
        methods=["POST"],
        endpoint="eufy_captcha_request",
    )
    @routes.login_required
    def eufy_captcha_request():
        """Disabled: native captcha flow stays off in bridge/emulator deployments."""
        profile = (request.form.get("profile") or "").strip().lower() or "default"
        routes.flash(
            "Eufy API/web captcha flow is disabled. Use the external bridge or VM / Emulator integration.",
            "info",
        )
        return redirect(url_for("ui.eufy_home", profile=profile))

    @bp.route(
        "/integrations/eufy/webportal/bootstrap",
        methods=["POST"],
        endpoint="eufy_webportal_bootstrap",
    )
    @routes.login_required
    def eufy_webportal_bootstrap():
        """Disabled: web portal bootstrap stays off in bridge/emulator deployments."""
        profile = (request.form.get("profile") or "").strip().lower() or "default"
        routes.flash(
            "Eufy web portal bootstrap is disabled. Use the external bridge or VM / Emulator integration.",
            "info",
        )
        return redirect(url_for("ui.eufy_home", profile=profile))

    @bp.route(
        "/integrations/eufy/devices",
        methods=["GET", "POST"],
        endpoint="eufy_devices",
    )
    @routes.login_required
    def eufy_devices():
        """List Eufy bridge devices and import them as Glimpser templates."""

        from app.utils import eufy_cloud, eufy_first_pass

        def _resolve_profile_or_fallback(raw_name: str) -> str:
            requested = str(raw_name or "").strip().lower() or "default"
            names = eufy_cloud.list_profile_names()
            if requested not in names:
                requested = "default"
            if requested != "default":
                return requested
            if eufy_cloud.configured("default"):
                return "default"
            for candidate in names:
                if candidate == "default":
                    continue
                if eufy_cloud.configured(candidate):
                    return candidate
            return requested

        # Prefer submitted form profile on POST to avoid query-string drift
        # when users keep multiple integration tabs open.
        profile = _resolve_profile_or_fallback(
            request.form.get("profile") or request.args.get("profile") or ""
        )
        list_error = ""
        requested_group = (
            request.form.get("group") or request.args.get("group") or ""
        ).strip()
        default_group = (
            validate_group_name(requested_group)
            or validate_group_name("" if profile == "default" else profile)
            or "eufy"
        )

        if request.method == "POST":
            action = str(request.form.get("action") or "import").strip().lower()
            timeout_raw = str(request.form.get("first_pass_timeout") or "20").strip()
            try:
                first_pass_timeout = float(timeout_raw)
            except Exception:
                first_pass_timeout = 20.0
            first_pass_timeout = max(5.0, min(first_pass_timeout, 60.0))

            if action == "first_pass":
                try:
                    results = eufy_first_pass.capture_profile_first_pass(
                        profile,
                        timeout=first_pass_timeout,
                    )
                except Exception as exc:
                    routes.flash(f"First pass failed: {exc}", "error")
                    return redirect(url_for("ui.eufy_devices", profile=profile))

                total = len(results)
                ok = sum(1 for row in results if row.get("ok"))
                failed_rows = [row for row in results if not row.get("ok")]
                failed = len(failed_rows)

                if total == 0:
                    routes.flash(
                        f"No imported eufy:// templates found for profile '{profile}'.",
                        "info",
                    )
                elif failed == 0:
                    routes.flash(
                        f"First pass complete: {ok}/{total} screenshots captured.",
                        "success",
                    )
                else:
                    summary = ", ".join(
                        f"{row['name']}: {str(row['error'])[:80]}"
                        for row in failed_rows[:3]
                    )
                    routes.flash(
                        f"First pass: {ok} ok, {failed} failed. {summary}",
                        "warning",
                    )
                return redirect(url_for("ui.eufy_devices", profile=profile))

            device_ids = [str(d).strip() for d in request.form.getlist("device_id")]
            group = (request.form.get("group") or "").strip() or default_group
            frequency = int(request.form.get("frequency") or 2)
            run_first_pass = str(request.form.get("run_first_pass") or "").lower() in {
                "1",
                "true",
                "on",
                "yes",
            }

            templates = routes.template_manager.get_templates()
            existing_names = set(templates.keys())
            imported = 0
            updated = 0
            deduped = 0
            imported_names: list[str] = []

            # Keep one template per (profile, device_id). Re-imports can happen
            # after captcha/session hiccups; this avoids accumulating duplicates.
            eufy_templates_by_device: dict[str, list[tuple[str, dict[str, object]]]] = (
                {}
            )
            for template_name, tmpl in templates.items():
                tmpl_url = str(tmpl.get("url") or "")
                if not tmpl_url.startswith("eufy://"):
                    continue
                try:
                    tmpl_profile, tmpl_device_id = eufy_cloud.parse_eufy_url(tmpl_url)
                except Exception:
                    continue
                if tmpl_profile != profile or not tmpl_device_id:
                    continue
                eufy_templates_by_device.setdefault(tmpl_device_id, []).append(
                    (template_name, tmpl)
                )

            canonical_by_device: dict[str, str] = {}
            for tmpl_device_id, variants in eufy_templates_by_device.items():
                ranked = sorted(
                    variants,
                    key=lambda item: (
                        # Prefer templates that already captured at least once.
                        (
                            1
                            if str(item[1].get("last_screenshot_time") or "").strip()
                            else 0
                        ),
                        # Prefer human-readable names over "-2/-3" suffixes.
                        1 if not re.search(r"-\d+$", item[0]) else 0,
                        # Prefer currently healthy templates over failed ones.
                        1 if not bool(item[1].get("capture_failed")) else 0,
                        int(item[1].get("id") or 0),
                    ),
                    reverse=True,
                )
                keep_name = ranked[0][0]
                canonical_by_device[tmpl_device_id] = keep_name
                for drop_name, _drop_tmpl in ranked[1:]:
                    if routes.template_manager.delete_template(drop_name):
                        deduped += 1
                        existing_names.discard(drop_name)

            for device_id in device_ids:
                if not device_id:
                    continue
                label = (
                    request.form.get(f"label_{device_id}") or f"Eufy_{device_id[:8]}"
                ).strip()

                existing_name = canonical_by_device.get(device_id)
                if existing_name:
                    ok = routes.template_manager.save_template(
                        existing_name,
                        {
                            "url": f"eufy://{profile}/{device_id}",
                            "groups": group,
                            "frequency": frequency,
                            "browser": False,
                            "stealth": False,
                            "headless": False,
                            "dark": True,
                            "notes": "Imported from Eufy integration.",
                        },
                    )
                    if ok:
                        updated += 1
                        imported_names.append(existing_name)
                    else:
                        logging.warning(
                            "eufy import update failed profile=%s name=%s device_id=%s",
                            profile,
                            existing_name,
                            device_id,
                        )
                    continue

                tname = _make_template_name(label, existing_names)
                ok = routes.template_manager.save_template(
                    tname,
                    {
                        "url": f"eufy://{profile}/{device_id}",
                        "groups": group,
                        "frequency": frequency,
                        "browser": False,
                        "stealth": False,
                        "headless": False,
                        "dark": True,
                        "notes": "Imported from Eufy integration.",
                    },
                )
                if ok:
                    imported += 1
                    imported_names.append(tname)
                else:
                    logging.warning(
                        "eufy import failed profile=%s name=%s device_id=%s",
                        profile,
                        tname,
                        device_id,
                    )

            if imported or updated or deduped:
                parts: list[str] = []
                if imported:
                    parts.append(f"imported {imported}")
                if updated:
                    parts.append(f"updated {updated}")
                if deduped:
                    parts.append(f"removed {deduped} duplicate(s)")
                routes.flash(
                    f"Eufy sync complete: {', '.join(parts)}.",
                    "success",
                )
                if run_first_pass and imported_names:
                    try:
                        pass_results = eufy_first_pass.capture_profile_first_pass(
                            profile,
                            timeout=first_pass_timeout,
                            template_names=imported_names,
                        )
                    except Exception as exc:
                        routes.flash(
                            f"Import complete, but first-pass capture failed: {exc}",
                            "warning",
                        )
                    else:
                        pass_ok = sum(1 for row in pass_results if row.get("ok"))
                        pass_failed = sum(
                            1 for row in pass_results if not row.get("ok")
                        )
                        if pass_failed == 0:
                            routes.flash(
                                f"First pass complete: {pass_ok}/{len(pass_results)} captured.",
                                "success",
                            )
                        else:
                            routes.flash(
                                f"First pass: {pass_ok} ok, {pass_failed} failed.",
                                "warning",
                            )
                primary_group = (group.split(",")[0] or "").strip()
                if primary_group:
                    return redirect(
                        routes.url_for("views.group_page", group_name=primary_group)
                    )
            else:
                routes.flash("No cameras imported.", "info")
            return redirect(url_for("ui.eufy_devices", profile=profile, group=group))

        if not eufy_cloud.configured(profile):
            routes.flash(
                f"Eufy profile '{profile}' is not configured yet.",
                "error",
            )
            return redirect(url_for("ui.eufy_home", profile=profile))

        try:
            devices = eufy_cloud.list_devices(profile)
        except Exception as exc:
            list_error = str(exc)
            routes.flash(f"Failed to list Eufy devices: {list_error}", "error")
            devices = []

        return render_template(
            "eufy_devices.html",
            devices=devices,
            profile=profile,
            list_error=list_error,
            default_group=default_group,
            page_title="Eufy Cameras",
        )

    @bp.route(
        "/integrations/eufy/snapshot",
        methods=["GET"],
        endpoint="eufy_snapshot_proxy",
    )
    def eufy_snapshot_proxy():
        """Proxy Eufy snapshots through Glimpser for enclosed capture URLs."""

        from app.utils import eufy_cloud

        profile = (request.args.get("profile") or "").strip().lower() or "default"
        device_id = str(request.args.get("device_id") or "").strip()
        token = str(request.args.get("token") or "").strip()

        if not device_id:
            abort(400, "device_id required")

        # Allow logged-in users directly. Background capture workers use signed
        # tokens in `eufy://`-derived URLs.
        if not bool(getattr(current_user, "is_authenticated", False)):
            verified = eufy_cloud.verify_snapshot_token(token)
            if not verified:
                abort(403)
            vp, vd = verified
            if vp != profile or vd != device_id:
                abort(403)

        source_headers = {}
        try:
            payload, content_type = eufy_cloud.fetch_snapshot(
                profile, device_id, timeout=20, response_headers=source_headers
            )
        except Exception as exc:
            logging.warning(
                "eufy snapshot proxy failed profile=%s device=%s: %s",
                profile,
                device_id,
                exc,
            )
            return Response(str(exc), status=502, mimetype="text/plain")

        resp = Response(payload, mimetype=content_type or "image/jpeg")
        if source_headers.get("Last-Modified"):
            resp.headers["Last-Modified"] = source_headers["Last-Modified"]
        resp.headers["Cache-Control"] = "no-store, max-age=0"
        return resp

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
