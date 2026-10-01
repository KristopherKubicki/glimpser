from __future__ import annotations

import os

from flask import Blueprint


def create_blueprint() -> Blueprint:
    """Create and return the media blueprint."""

    from app import routes

    bp = Blueprint("media", __name__)

    @bp.route("/screenshots/<string:name>")
    @routes.login_required
    def list_screenshots(name: routes.TemplateName):
        """Return a JSON list of screenshot files for ``name``."""

        template_name = routes.validate_template_name(str(name))
        if template_name is None:
            routes.abort(404)

        lscreens = routes.template_manager.get_screenshots_for_template(template_name)
        return routes.jsonify({"screenshots": lscreens})

    @bp.route("/screenshots/<string:name>/<string:filename>")
    @routes.login_required
    def view_screenshot(name: routes.TemplateName, filename: str):
        """Serve a screenshot file for a template.

        Args:
            name: Template name provided in the URL.
            filename: Name of the screenshot file to return.

        Raises:
            werkzeug.exceptions.NotFound: If the template name or file is
                invalid or the directory is missing.
        """
        template_name = routes.validate_template_name(str(name))
        if template_name is None or not routes.allowed_filename(filename):
            routes.abort(404)

        path = os.path.join(
            os.path.dirname(os.path.join(__file__)),
            "..",
            routes.SCREENSHOT_DIRECTORY,
            str(template_name),
        )

        if not os.path.exists(path):
            routes.abort(404)

        return routes.send_from_directory(path, filename)

    @bp.route("/videos/<string:name>")
    @routes.login_required
    def list_videos(name: routes.TemplateName):
        """Return a JSON list of video files for ``name``."""

        template_name = routes.validate_template_name(str(name))
        if template_name is None:
            routes.abort(404)

        lvideos = routes.template_manager.get_videos_for_template(template_name)
        return routes.jsonify({"videos": lvideos})

    @bp.route("/videos/<string:name>/<string:filename>")
    @routes.login_required
    def view_video(name: routes.TemplateName, filename: str):
        """Serve a video file for a template.

        Args:
            name: Template name provided in the URL.
            filename: Name of the video file to return.

        Raises:
            werkzeug.exceptions.NotFound: If the template name or file is
                invalid or the directory is missing.
        """
        template_name = routes.validate_template_name(str(name))
        if template_name is None or not routes.allowed_filename(filename):
            routes.abort(404)

        path = os.path.join(
            os.path.dirname(os.path.join(__file__)),
            "..",
            routes.VIDEO_DIRECTORY,
            str(template_name),
        )

        if not os.path.exists(path):
            routes.abort(404)

        return routes.send_from_directory(path, filename)

    @bp.route("/api/sms-media/v1/render")
    @routes.login_required
    def render_sms_media():
        """Render a compact stamped GIF for SMS/MMS use."""

        from app.utils.sms_media import (
            DEFAULT_FRAME_DURATION_MS,
            DEFAULT_FRAMES,
            DEFAULT_LONG_EDGE,
            DEFAULT_MAX_BYTES,
            SmsMediaError,
            render_sms_event_buffer_gif,
            render_sms_gif,
        )
        from app.utils.sms_media_storage import (
            SmsMediaStorageConfigError,
            SmsMediaStoragePublishError,
            publish_sms_media,
        )

        camera = (
            routes.request.args.get("camera")
            or routes.request.args.get("profile")
            or ""
        ).strip()
        media_format = (routes.request.args.get("format") or "auto").strip().lower()
        mode = (routes.request.args.get("mode") or "auto").strip().lower()
        if media_format not in {"auto", "gif"}:
            routes.abort(400, "SMS media endpoint currently renders GIF only")
        if mode not in {"auto", "gif", "motion_gif", "event_buffer"}:
            routes.abort(400, "Unsupported SMS media mode")

        max_age_raw = routes.request.args.get("max_age_seconds")
        max_age_seconds = int(max_age_raw) if max_age_raw else None
        try:
            renderer = (
                render_sms_event_buffer_gif
                if mode in {"event_buffer", "motion_gif"}
                else render_sms_gif
            )
            source_root = (
                routes.event_buffer.EVENT_BUFFER_ROOT
                if renderer is render_sms_event_buffer_gif
                else routes.SCREENSHOT_DIRECTORY
            )
            asset = renderer(
                camera,
                source_root,
                long_edge=routes.request.args.get("long_edge", DEFAULT_LONG_EDGE),
                max_bytes=routes.request.args.get("max_bytes", DEFAULT_MAX_BYTES),
                frames=routes.request.args.get("frames", DEFAULT_FRAMES),
                frame_duration_ms=routes.request.args.get(
                    "frame_duration_ms", DEFAULT_FRAME_DURATION_MS
                ),
                max_age_seconds=max_age_seconds,
            )
        except ValueError:
            routes.abort(400, "Invalid SMS media option")
        except SmsMediaError as exc:
            routes.abort(exc.status_code, str(exc))

        metadata = routes.request.args.get("metadata", "").lower() in {
            "1",
            "true",
            "yes",
        }
        publish = routes.request.args.get("publish", "").lower() in {
            "1",
            "true",
            "yes",
        }
        if metadata or publish:
            payload = {
                "ok": True,
                "camera": asset.camera,
                "content_type": asset.content_type,
                "bytes": asset.bytes,
                "frames": asset.frames,
                "long_edge": asset.long_edge,
                "source_age_seconds": asset.source_age_seconds,
                "latest_source": asset.latest_source,
                "transform": asset.transform,
                "media_key": asset.media_key,
                "expires_seconds": 300,
            }
            if publish:
                try:
                    published = publish_sms_media(
                        camera=asset.camera,
                        body=asset.body,
                        content_type=asset.content_type,
                        extension="gif",
                    )
                except SmsMediaStorageConfigError as exc:
                    routes.abort(503, str(exc))
                except SmsMediaStoragePublishError as exc:
                    routes.abort(502, str(exc))
                payload.update(
                    {
                        "key": published.key,
                        "media_url": published.media_url,
                        "expires_at": published.expires_at,
                        "expires_seconds": published.expires_seconds,
                    }
                )
            return routes.jsonify(payload)

        response = routes.Response(asset.body, mimetype=asset.content_type)
        response.headers["Cache-Control"] = "private, max-age=300"
        response.headers["Content-Length"] = str(asset.bytes)
        response.headers["X-Glimpser-Camera"] = asset.camera
        response.headers["X-Glimpser-Source-Age-Seconds"] = str(
            asset.source_age_seconds or 0
        )
        response.headers["X-Glimpser-Transform"] = asset.transform
        response.headers["X-Glimpser-Media-Key"] = asset.media_key
        response.headers["X-Glimpser-Frames"] = str(asset.frames)
        return response

    return bp
