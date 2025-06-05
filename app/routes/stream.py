from flask import Blueprint, request, abort, Response, stream_with_context
from . import (
    template_manager,
    generate_fast_mjpg,
    rtsp_sessions,
    generate,
    generate_video_stream,
    generate_live_stream,
    validate_template_name,
    VIDEO_DIRECTORY,
)
import os
import re

bp = Blueprint("stream", __name__)


@bp.route("/fast_stream.mjpg", methods=["GET"])
def fast_stream_mjpg():
    from . import login_required

    @login_required
    def handler():
        camera = request.args.get("camera")
        if not camera:
            abort(400, "camera parameter required")
        if not template_manager.get_template(camera):
            abort(404)
        return Response(
            generate_fast_mjpg(camera),
            mimetype="multipart/x-mixed-replace; boundary=frame",
        )

    return handler()


@bp.route("/rtsp_stream")
def rtsp_stream():
    from . import login_required

    @login_required
    def handler():
        session_id = request.args.get("session")
        if (
            session_id not in rtsp_sessions
            or rtsp_sessions[session_id]["state"] != "PLAYING"
        ):
            abort(400, "Invalid session or session not in PLAYING state")
        return Response(
            generate(rtsp=True, session_id=session_id),
            mimetype="application/x-rtp",
        )

    return handler()


@bp.route("/stream.mp4")
def stream_mp4():
    from . import login_required

    @login_required
    def handler():
        camera = request.args.get("camera")
        if camera:
            camera = validate_template_name(camera)
            if camera is None:
                abort(400, "Invalid camera name")
            video_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "..",
                VIDEO_DIRECTORY,
                camera,
                "in_process.mp4",
            )
            if not os.path.exists(video_path):
                abort(404)
            return Response(
                stream_with_context(generate_video_stream(video_path)),
                mimetype="video/mp4",
            )

        lgroup = "all"
        group = request.args.get("group")
        if group and re.match(r"^[a-zA-Z0-9_]+$", group):
            lgroup = group
        else:
            if group:
                abort(400, "Invalid group name. Group name must be alphanumeric.")
        lgroup = os.path.basename(lgroup)
        video_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "..",
            VIDEO_DIRECTORY,
            f"{lgroup}_in_process.mp4",
        )
        if not os.path.exists(video_path):
            abort(404)
        return Response(
            stream_with_context(generate_video_stream(video_path)),
            mimetype="video/mp4",
        )

    return handler()


@bp.route("/live_video")
def live_video():
    from . import login_required

    @login_required
    def handler():
        camera = request.args.get("camera")
        if not camera:
            abort(400, "camera parameter required")
        details = template_manager.get_template(camera)
        if not details:
            abort(404)
        url = details.get("url")
        if not url:
            abort(404)
        return Response(
            stream_with_context(generate_live_stream(url)),
            mimetype="video/mp4",
        )

    return handler()


@bp.route("/stream.m3u8")
def playlist_m3u8():
    from . import login_required

    @login_required
    def handler():
        path = os.path.join(
            os.path.dirname(os.path.join(__file__)), "..", VIDEO_DIRECTORY
        )
        if not os.path.exists(path):
            abort(404)

    camera = request.args.get("camera")
    group = request.args.get("group")

    playlist_content = "#EXTM3U\n"
    playlist_content += "#EXT-X-VERSION:3\n"
    playlist_content += "#EXT-X-TARGETDURATION:10\n"
    playlist_content += "#EXT-X-MEDIA-SEQUENCE:0\n"

    templates = template_manager.get_templates()

    filtered_templates = []
    if camera:
        camera = validate_template_name(camera)
        if camera is None:
            abort(400, "Invalid camera name")
        details = templates.get(camera)
        if details:
            filtered_templates.append((camera, details))
    elif group:
        if not re.match(r"^[a-zA-Z0-9_]+$", group):
            abort(400, "Invalid group name. Group name must be alphanumeric.")
        for name, details in templates.items():
            groups = [g.strip() for g in details.get("groups", "").split(",")]
            if group in groups:
                valid = validate_template_name(name)
                if valid:
                    filtered_templates.append((valid, details))
    else:
        for name, details in templates.items():
            valid = validate_template_name(name)
            if valid:
                filtered_templates.append((valid, details))

    sorted_templates = sorted(
        filtered_templates,
        key=lambda x: (x[1].get("last_video_time", 0) or 0),
        reverse=True,
    )

    from . import generate_timed_hash, request as req

    for camera_name, _ in sorted_templates:
        lkey = generate_timed_hash()
        video_path = f"{req.url_root}last_video/{camera_name}?timed_key={lkey}"
        playlist_content += f"#EXTINF:10.0,{camera_name}\n{video_path}\n"

        playlist_content += "#EXT-X-ENDLIST\n"
        return Response(playlist_content, mimetype="application/x-mpegURL")

    return handler()
