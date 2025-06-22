from __future__ import annotations

from flask import Blueprint, Response


def create_blueprint() -> Blueprint:
    """Create and return the streaming blueprint."""

    import app.routes as routes

    bp = Blueprint("stream", __name__)

    @bp.route("/test.mjpg", methods=["GET"])
    @routes.login_required
    def test_mjpg():
        group = routes.request.args.get("group")
        camera = routes.request.args.get("camera")
        if group == "all":
            group = None
        if camera == "all":
            camera = None
        return Response(
            routes.generate(group=group, camera=camera, filename="latest_camera.png"),
            mimetype="multipart/x-mixed-replace; boundary=frame",
        )

    @bp.route("/stream.mjpg", methods=["GET"])
    @routes.login_required
    def stream_mjpg():
        group = routes.request.args.get("group")
        camera = routes.request.args.get("camera")
        if group == "all":
            group = None
        if camera == "all":
            camera = None
        return Response(
            routes.generate(group=group, camera=camera, filename="latest_camera.png"),
            mimetype="multipart/x-mixed-replace; boundary=frame",
        )

    return bp
