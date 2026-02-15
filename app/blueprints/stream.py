from __future__ import annotations

from flask import Blueprint, Response


def create_blueprint() -> Blueprint:
    """Create and return the streaming blueprint."""

    from app import routes

    bp = Blueprint("stream", __name__)

    @bp.route("/test.mjpg", methods=["GET"])
    @routes.login_required
    def test_mjpg():
        """Stream the latest MJPEG frames for quick validation.

        Query Parameters:
            group: Optional group name used to filter templates.
            camera: Optional camera name used to filter frames.

        Returns:
            Response: Multipart MJPEG response of screenshot frames.
        """

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
        """Stream the primary MJPEG feed.

        Query Parameters:
            group: Optional group filter applied to templates.
            camera: Optional camera filter applied to frames.

        Returns:
            Response: Multipart MJPEG response of screenshot frames.
        """

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

    @bp.route("/stream.png")
    @routes.login_required
    def stream_png() -> Response:
        """Serve the latest screenshot for a camera or group."""

        group = routes.request.args.get("group")
        camera = routes.request.args.get("camera")
        if group == "all":
            group = None
        if camera == "all":
            camera = None

        if camera:
            camera = routes.validate_template_name(camera)
            if camera is None:
                routes.abort(400, "Invalid camera name")
            cam_path = routes.os.path.join(
                routes.os.path.dirname(routes.os.path.abspath(__file__)),
                "..",
                routes.SCREENSHOT_DIRECTORY,
                camera,
                "latest_camera.png",
            )
            if routes.os.path.exists(cam_path) and routes.screenshots._is_valid_png(
                cam_path
            ):
                return routes.send_conditional_file(cam_path, routes.PNG_TTL_SEC)
            routes.abort(404)

        if group:
            from app.utils.validators import validate_group_name

            group = validate_group_name(group)
            if group is None:
                routes.abort(400, "Invalid group name")
            group_path = routes.os.path.join(
                routes.os.path.dirname(routes.os.path.abspath(__file__)),
                "..",
                routes.SCREENSHOT_DIRECTORY,
                f"{group}_latest_camera.png",
            )
            if routes.os.path.exists(group_path) and routes.screenshots._is_valid_png(
                group_path
            ):
                return routes.send_conditional_file(group_path, routes.PNG_TTL_SEC)
            routes.abort(404)

        latest_path = routes.os.path.join(
            routes.os.path.dirname(routes.os.path.abspath(__file__)),
            "..",
            routes.SCREENSHOT_DIRECTORY,
            "latest_camera.png",
        )
        if routes.os.path.exists(latest_path):
            if routes.screenshots._is_valid_png(latest_path):
                return routes.send_conditional_file(latest_path, routes.PNG_TTL_SEC)
            routes.logging.warning(
                "Invalid latest camera image removed: %s", latest_path
            )
            try:
                routes.os.remove(latest_path)
            except OSError as exc:  # pragma: no cover - unexpected removal issue
                routes.logging.warning(
                    "Failed to remove invalid latest image %s: %s", latest_path, exc
                )

        if (
            routes.last_time
            and routes.time.time() - routes.last_time < 1
            and routes.last_shot
            and routes.os.path.exists(routes.last_shot)
        ):
            return routes.send_conditional_file(routes.last_shot, routes.PNG_TTL_SEC)

        templates = routes.template_manager.get_templates()
        sorted_templates = sorted(
            templates.items(),
            key=lambda x: x[1].get("last_screenshot_time", 0) or 0,
            reverse=True,
        )

        most_recent_time = 0
        most_recent_file = None
        last_file = None
        for _, template in sorted_templates:
            name = routes.validate_template_name(template.get("name"))
            if name is None:
                continue
            path = routes.os.path.join(
                routes.os.path.dirname(routes.os.path.abspath(__file__)),
                "..",
                routes.SCREENSHOT_DIRECTORY,
                name,
            )
            files_with_mtime = []
            for f in routes.glob.glob(path + "/*.png"):
                if not routes.os.path.isfile(f) or f.endswith(".tmp.png"):
                    continue
                try:
                    mtime = routes.os.path.getmtime(f)
                except OSError:
                    continue
                if not routes.screenshots._is_valid_png(f):
                    continue
                files_with_mtime.append((f, mtime))
            if not files_with_mtime:
                continue
            files_with_mtime.sort(key=lambda t: t[1])
            last_file, last_mtime = files_with_mtime[-1]
            if last_mtime > most_recent_time:
                most_recent_file = last_file
                most_recent_time = last_mtime
        if most_recent_file is None:
            if routes.last_shot and routes.os.path.exists(routes.last_shot):
                return routes.send_conditional_file(
                    routes.last_shot, routes.PNG_TTL_SEC
                )
            routes.abort(404)

        routes.last_time = routes.time.time()
        routes.last_shot = most_recent_file

        if routes.os.path.exists(most_recent_file) and routes.screenshots._is_valid_png(
            most_recent_file
        ):
            return routes.send_conditional_file(most_recent_file, routes.PNG_TTL_SEC)
        if (
            last_file
            and routes.os.path.exists(last_file)
            and routes.screenshots._is_valid_png(last_file)
        ):
            routes.last_shot = last_file
            return routes.send_conditional_file(last_file, routes.PNG_TTL_SEC)
        if (
            routes.last_shot
            and routes.os.path.exists(routes.last_shot)
            and routes.screenshots._is_valid_png(routes.last_shot)
        ):
            return routes.send_conditional_file(routes.last_shot, routes.PNG_TTL_SEC)

    @bp.route(
        "/test.rtsp",
        methods=[
            "OPTIONS",
            "DESCRIBE",
            "SETUP",
            "PLAY",
            "PAUSE",
            "GET_PARAMETER",
            "TEARDOWN",
        ],
    )
    @routes.login_required
    def handle_rtsp() -> Response:
        """Handle RTSP handshake and control messages."""

        session_id = routes.request.headers.get("Session", str(routes.uuid.uuid4()))
        cseq = routes.request.headers.get("CSeq", "0")

        if routes.request.method == "OPTIONS":
            return Response(
                "Public: OPTIONS, DESCRIBE, SETUP, PLAY, PAUSE, GET_PARAMETER, TEARDOWN",
                headers={"CSeq": cseq},
            )

        elif routes.request.method == "DESCRIBE":
            sdp = (
                "v=0\r\n"
                "o=- 0 0 IN IP4 127.0.0.1\r\n"
                "s=Glimpser RTSP Stream\r\n"
                "t=0 0\r\n"
                "m=video 0 RTP/AVP 26\r\n"
                "a=rtpmap:26 JPEG/90000\r\n"
                "a=control:streamid=0\r\n"
            )
            return Response(
                sdp,
                mimetype="application/sdp",
                headers={"CSeq": cseq, "Content-Base": routes.request.url},
            )

        elif routes.request.method == "SETUP":
            if session_id not in routes.rtsp_sessions:
                routes.rtsp_sessions[session_id] = {
                    "state": "READY",
                    "seq": routes.random.randint(0, 65535),
                    "timestamp": routes.random.randint(0, 0xFFFFFFFF),
                    "ssrc": routes.random.randint(0, 0xFFFFFFFF),
                    "last_keepalive": routes.time.time(),
                }

            transport = routes.request.headers.get("Transport", "")
            client_ports = (0, 0)
            match = routes.re.search(r"client_port=(\d+)(?:-(\d+))?", transport)
            if match:
                first = int(match.group(1))
                second = int(match.group(2) or first + 1)
                client_ports = (first, second)

            server_ports = (5004, 5005)
            session = routes.rtsp_sessions[session_id]
            session["client_ports"] = client_ports
            session["server_ports"] = server_ports

            transport_response = transport
            if transport_response and not transport_response.endswith(";"):
                transport_response += ";"
            transport_response += f"server_port={server_ports[0]}-{server_ports[1]};ssrc={session['ssrc']}"

            return Response(
                headers={
                    "CSeq": cseq,
                    "Session": session_id,
                    "Transport": transport_response,
                }
            )

        elif routes.request.method == "PLAY":
            if session_id not in routes.rtsp_sessions:
                routes.abort(454)  # Session Not Found
            routes.rtsp_sessions[session_id]["state"] = "PLAYING"
            return Response(
                headers={
                    "CSeq": cseq,
                    "Session": session_id,
                    "RTP-Info": "url=rtsp://example.com/test.rtsp/streamid=0;seq=0;rtptime=0",
                }
            )

        elif routes.request.method == "PAUSE":
            if session_id not in routes.rtsp_sessions:
                routes.abort(454)
            routes.rtsp_sessions[session_id]["state"] = "PAUSED"
            return Response(headers={"CSeq": cseq, "Session": session_id})

        elif routes.request.method == "GET_PARAMETER":
            if session_id not in routes.rtsp_sessions:
                routes.abort(454)
            routes.rtsp_sessions[session_id]["last_keepalive"] = routes.time.time()
            return Response(headers={"CSeq": cseq, "Session": session_id})

        elif routes.request.method == "TEARDOWN":
            if session_id in routes.rtsp_sessions:
                del routes.rtsp_sessions[session_id]
            return Response(headers={"CSeq": cseq, "Session": session_id})

        return "Method Not Allowed", 405

    @bp.route("/motion.mjpg", methods=["GET"])
    @routes.login_required
    def motion_mjpg() -> Response:
        """Return a motion-only MJPEG stream."""

        group = routes.request.args.get("group")
        camera = routes.request.args.get("camera")
        if group == "all":
            group = None
        if camera == "all":
            camera = None
        return Response(
            routes.generate(group=group, camera=camera, filename="last_motion.png"),
            mimetype="multipart/x-mixed-replace; boundary=frame",
        )

    @bp.route("/caption.mjpg", methods=["GET"])
    @routes.login_required
    def caption_mjpg() -> Response:
        """Return the last caption MJPEG stream."""

        group = routes.request.args.get("group")
        camera = routes.request.args.get("camera")
        if group == "all":
            group = None
        if camera == "all":
            camera = None
        routes.logging.debug("last caption")
        return Response(
            routes.generate(group=group, camera=camera, filename="last_caption.png"),
            mimetype="multipart/x-mixed-replace; boundary=frame",
        )

    @bp.route("/internal_caption.mjpg", methods=["GET"])
    @routes.login_required
    def internal_caption_mjpg() -> Response:
        """Stream caption images in real time."""

        group = routes.request.args.get("group")
        camera = routes.request.args.get("camera")
        return Response(
            routes.generate_caption_loop(group=group, camera=camera),
            mimetype="multipart/x-mixed-replace; boundary=frame",
        )

    @bp.route("/motion_caption.mjpg", methods=["GET"])
    @routes.login_required
    def motion_caption_mjpg() -> Response:
        """Return a motion-only caption MJPEG stream."""

        group = routes.request.args.get("group")
        camera = routes.request.args.get("camera")
        if group == "all":
            group = None
        if camera == "all":
            camera = None
        routes.logging.debug("last motion caption")
        return Response(
            routes.generate(
                group=group, camera=camera, filename="last_motion_caption.png"
            ),
            mimetype="multipart/x-mixed-replace; boundary=frame",
        )

    @bp.route("/test_pattern.mjpg", methods=["GET"])
    @routes.login_required
    def test_pattern_mjpg() -> Response:
        """Serve an animated test pattern stream."""

        spinner_frames = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
        index = 0

        def generate_pattern() -> routes.Generator[bytes, None, None]:
            nonlocal index
            boundary = b"frame"
            while True:
                spinner = spinner_frames[index % len(spinner_frames)]
                img = routes.test_pattern.generate_test_pattern(spinner=spinner)
                frame = routes.test_pattern.encode_jpeg_with_metadata(img)
                yield b"--" + boundary + b"\r\n"
                yield b"Content-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
                index += 1
                routes.time.sleep(1.0)

        return Response(
            generate_pattern(),
            mimetype="multipart/x-mixed-replace; boundary=frame",
        )

    @bp.route("/fast_stream.mjpg", methods=["GET"])
    @routes.login_required
    def fast_stream_mjpg() -> Response:
        """Return a high frame rate MJPEG stream."""

        camera = routes.request.args.get("camera")
        if not camera:
            routes.abort(400, "camera parameter required")
        if not routes.template_manager.get_template(camera):
            routes.abort(404)
        return Response(
            routes.generate_fast_mjpg(camera),
            mimetype="multipart/x-mixed-replace; boundary=frame",
        )

    @bp.route("/rtsp_stream")
    def rtsp_stream() -> Response:
        """Return RTP packets for an active RTSP session."""

        session_id = routes.request.args.get("session")
        if (
            session_id not in routes.rtsp_sessions
            or routes.rtsp_sessions[session_id]["state"] != "PLAYING"
        ):
            routes.abort(400, "Invalid session or session not in PLAYING state")
        return Response(
            routes.generate(rtsp=True, session_id=session_id),
            mimetype="application/x-rtp",
        )

    @bp.route("/stream.mp4")
    @routes.login_required
    def stream_mp4() -> Response:
        """Stream the latest MP4 video."""

        camera = routes.request.args.get("camera")
        if camera:
            camera = routes.validate_template_name(camera)
            if camera is None:
                routes.abort(400, "Invalid camera name")
            video_path = routes.os.path.join(
                routes.os.path.dirname(routes.os.path.abspath(__file__)),
                "..",
                routes.VIDEO_DIRECTORY,
                camera,
                "in_process.mp4",
            )
            if not routes.os.path.exists(video_path):
                routes.abort(404)
            return Response(
                routes.stream_with_context(routes.generate_video_stream(video_path)),
                mimetype="video/mp4",
            )

        lgroup = "all"
        group = routes.request.args.get("group")
        if group and routes.re.match(r"^[a-zA-Z0-9_]+$", group):
            lgroup = group
        elif group:
            routes.abort(400, "Invalid group name. Group name must be alphanumeric.")

        lgroup = routes.secure_filename(lgroup)
        video_path = routes.os.path.join(
            routes.os.path.dirname(routes.os.path.abspath(__file__)),
            "..",
            routes.VIDEO_DIRECTORY,
            f"{lgroup}_in_process.mp4",
        )

        if not routes.os.path.exists(video_path):
            routes.abort(404)

        return Response(
            routes.stream_with_context(routes.generate_video_stream(video_path)),
            mimetype="video/mp4",
        )

    @bp.route("/live_video")
    @routes.login_required
    def live_video() -> Response:
        """Stream live video from a configured URL."""

        camera = routes.request.args.get("camera")
        if not camera:
            routes.abort(400, "camera parameter required")
        details = routes.template_manager.get_template(camera)
        if not details:
            routes.abort(404)

        profile = (routes.request.args.get("profile") or "main").strip().lower()

        quality = (routes.request.args.get("quality") or "auto").strip().lower()
        if quality not in {"auto", "low", "high", "first"}:
            quality = "auto"

        if profile not in {"main", "sub", "auto"}:
            profile = "main"

        stream_url = routes.resolve_live_stream_url(details, profile=profile)
        url = stream_url or details.get("url")
        if not url:
            routes.abort(404)

        routes.logging.info(
            "live_video request camera=%s profile=%s source=%s",
            camera,
            profile,
            "stream" if stream_url else "fallback",
        )

        width = None
        fps = None
        if quality == "first":
            width = min(routes.config.LIVE_RTSP_WIDTH, 360)
            fps = min(routes.config.LIVE_RTSP_FPS, 2)
        elif quality == "low":
            width = min(routes.config.LIVE_RTSP_WIDTH, 480)
            fps = min(routes.config.LIVE_RTSP_FPS, 3)
        elif quality == "high":
            width = max(routes.config.LIVE_RTSP_WIDTH, 1280)
            width = min(width, 1920)
            fps = max(routes.config.LIVE_RTSP_FPS, 10)
            fps = min(fps, 15)

        resp = Response(
            routes.stream_with_context(
                routes.generate_live_stream(url, width=width, fps=fps)
            ),
            mimetype="video/mp4",
        )
        resp.headers["X-Live-Source"] = "stream" if stream_url else "fallback"
        resp.headers["X-Live-Profile"] = profile
        resp.headers["X-Live-Quality"] = quality
        return resp

    @bp.route("/stream.m3u8")
    @routes.login_required
    def playlist_m3u8() -> Response:
        """Generate an HLS playlist of recent videos."""

        path = routes.os.path.join(
            routes.os.path.dirname(routes.os.path.join(__file__)),
            "..",
            routes.VIDEO_DIRECTORY,
        )

        if not routes.os.path.exists(path):
            routes.abort(404)

        camera = routes.request.args.get("camera")
        group = routes.request.args.get("group")

        playlist_content = "#EXTM3U\n"
        playlist_content += "#EXT-X-VERSION:3\n"
        playlist_content += "#EXT-X-TARGETDURATION:10\n"
        playlist_content += "#EXT-X-MEDIA-SEQUENCE:0\n"

        templates = routes.template_manager.get_templates()

        filtered_templates = []
        if camera:
            camera = routes.validate_template_name(camera)
            if camera is None:
                routes.abort(400, "Invalid camera name")
            details = templates.get(camera)
            if details:
                filtered_templates.append((camera, details))
        elif group:
            if not routes.re.match(r"^[a-zA-Z0-9_]+$", group):
                routes.abort(
                    400, "Invalid group name. Group name must be alphanumeric."
                )
            for name, details in templates.items():
                groups = [g.strip() for g in details.get("groups", "").split(",")]
                if group in groups:
                    valid = routes.validate_template_name(name)
                    if valid:
                        filtered_templates.append((valid, details))
        else:
            for name, details in templates.items():
                valid = routes.validate_template_name(name)
                if valid:
                    filtered_templates.append((valid, details))

        sorted_templates = sorted(
            filtered_templates,
            key=lambda x: x[1].get("last_video_time", 0) or 0,
            reverse=True,
        )

        for camera_name, _ in sorted_templates:
            lkey = routes.generate_timed_hash()
            video_path = (
                f"{routes.request.url_root}last_video/{camera_name}?timed_key={lkey}"
            )
            playlist_content += f"#EXTINF:10.0,{camera_name}\n{video_path}\n"

        playlist_content += "#EXT-X-ENDLIST\n"

        return Response(playlist_content, mimetype="application/x-mpegURL")

    return bp
