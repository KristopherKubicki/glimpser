from __future__ import annotations

import os

from flask import Blueprint


def create_blueprint() -> Blueprint:
    """Create and return the media blueprint."""

    import app.routes as routes

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

    return bp
