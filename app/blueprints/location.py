"""Routes for Android-style shared location dashboards."""

from __future__ import annotations

import secrets
from datetime import UTC, datetime

from flask import Blueprint, jsonify, redirect, render_template, request, url_for

from app.utils import location_bridge
from app.utils.camera_catalog import build_camera_catalog
from app.utils.household_presence import presence_context
from app.utils.hubitat_locations import household_subjects, nearby_cameras
from app.utils.source_freshness import timestamp


def _bearer_token() -> str:
    auth_header = request.headers.get("Authorization", "")
    prefix = "Bearer "
    if auth_header.startswith(prefix):
        return auth_header[len(prefix) :].strip()
    return ""


def _submitted_token() -> str:
    return (
        _bearer_token()
        or request.headers.get("X-Location-Token", "")
        or request.headers.get("X-API-Token", "")
        or request.headers.get("X-API-Key", "")
        or request.values.get("location_token", "")
        or request.values.get("token", "")
        or request.values.get("api_key", "")
    ).strip()


def create_blueprint() -> Blueprint:
    """Create and return the shared-location blueprint."""

    from app import routes

    bp = Blueprint("location", __name__)

    def _configured_ingest_tokens() -> list[str]:
        return [
            token.strip()
            for token in (
                routes.config.get_setting("ANDROID_LOCATION_TOKEN", ""),
                routes.config.get_setting("LOCATION_INGEST_TOKEN", ""),
                routes.config.get_setting("API_KEY", ""),
            )
            if str(token or "").strip()
        ]

    def _ingest_authorized() -> bool:
        supplied = _submitted_token()
        if not supplied:
            return False
        return any(
            secrets.compare_digest(supplied, configured)
            for configured in _configured_ingest_tokens()
        )

    @bp.route("/integrations/android", endpoint="android_home")
    @routes.login_required
    @routes.profile_route("/integrations/android")
    def android_home():
        """Android bridge status and setup page."""

        points = location_bridge.list_latest_locations()
        return render_template(
            "android_home.html",
            locations=points,
            token_configured=bool(_configured_ingest_tokens()),
            page_title="Android Locations",
        )

    @bp.route("/integrations/android/map", endpoint="android_location_map")
    @bp.route("/android/location-map", endpoint="android_location_map_alias")
    @bp.route("/locations", endpoint="shared_location_map")
    @routes.login_required
    @routes.profile_route("/locations")
    def location_map():
        """Render the full-screen shared location map."""

        return render_template(
            "android_location_map.html",
            locations=location_bridge.list_latest_locations(),
            page_title="Shared Locations",
        )

    @bp.route("/api/locations", endpoint="api_locations")
    @routes.login_required
    @routes.profile_route("/api/locations")
    def api_locations():
        """Return latest normalized locations for all tracked subjects."""

        points = location_bridge.list_latest_locations()
        return jsonify(
            {
                "locations": points,
                "count": len(points),
                "generated_at": datetime.now(UTC).isoformat(),
            }
        )

    @bp.route("/api/nearby-context")
    @routes.login_required
    def nearby_context():
        """Combine reported presence with true GPS and public camera coordinates."""
        context = presence_context()
        subjects = context["subjects"]
        telemetry = {s["subject_id"]: s for s in household_subjects()}
        for subject in subjects:
            raw = telemetry.get(subject["subject_id"], {})
            subject["position"] = raw.get("position")
            subject["position_status"] = raw.get(
                "position_status", "GPS source not connected"
            )
        points = location_bridge.list_latest_locations()
        # GPS and home/away remain independent; a fresh coordinate is not an arrival.
        for subject in subjects:
            matching = [
                p for p in points if p.get("subject_id") == subject["subject_id"]
            ]
            for point in matching:
                fix = timestamp(point.get("timestamp"))
                if (
                    fix
                    and not point.get("stale")
                    and 0 <= (datetime.now(UTC) - fix).total_seconds() <= 300
                ):
                    subject["position"] = point
                    subject["position_status"] = (
                        "Fresh shared phone GPS; home/away not inferred"
                    )
        points.extend(
            subject["position"]
            for subject in subjects
            if subject.get("position") and subject["position"] not in points
        )
        catalog = build_camera_catalog(
            routes.template_manager.TemplateManager().get_templates()
        )
        cameras = catalog["cameras"]
        response = jsonify(
            {
                "subjects": subjects,
                "presence_events": context["presence_events"],
                "locations": points,
                **catalog,
                "nearby": nearby_cameras(points, cameras),
                "generated_at": datetime.now(UTC).isoformat(),
            }
        )
        response.headers["Cache-Control"] = "private, no-store"
        return response

    @bp.route("/api/household-presence")
    @routes.login_required
    def household_presence():
        """Return durable household presence without exposing exact locations."""
        response = jsonify(presence_context())
        response.headers["Cache-Control"] = "private, no-store"
        return response

    @bp.route(
        "/integrations/android/location",
        methods=["POST"],
        endpoint="android_location_ingest",
    )
    @routes.profile_route("/integrations/android/location")
    def android_location_ingest():
        """Accept a phone, Tasker, OwnTracks, or vehicle location update."""

        if not _ingest_authorized():
            return jsonify({"ok": False, "error": "unauthorized"}), 401
        payload = request.get_json(silent=True)
        if payload is None:
            payload = request.form.to_dict(flat=True)
        if not payload:
            payload = request.args.to_dict(flat=True)
        try:
            point = location_bridge.save_latest_location(
                payload,
                provider_default=str(payload.get("provider") or "android"),
            )
        except location_bridge.LocationPayloadError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        return jsonify({"ok": True, "location": point})

    @bp.route("/integrations/android/locations", endpoint="android_locations_legacy")
    @routes.login_required
    def android_locations_legacy():
        """Redirect older Android integration links to the full map."""

        return redirect(url_for("location.android_location_map"))

    return bp
