from __future__ import annotations

import io
from datetime import datetime
from typing import Any

from flask import Blueprint, Response, jsonify, redirect

_HIGH_FIDELITY_DEFAULT_EXCLUDE = (
    "private",
    "safe room",
    "safe_room",
    "vault",
    "jewel",
    "jewelry",
)

_HIGH_FIDELITY_BAD_CAPTION_TOKENS = (
    "unreadable",
    "no screenshot",
    "placeholder",
    "sign in",
    "captcha",
    "safety pin",
    "loading",
    "blank",
    "offline mode",
)

_HIGH_FIDELITY_CANDIDATE_CACHE_TTL_S = 90.0
_HIGH_FIDELITY_CANDIDATE_CACHE: dict[
    tuple[Any, tuple[str, ...], tuple[str, ...], int, int, bool],
    tuple[float, list[dict[str, Any]]],
] = {}


def _parse_high_fidelity_terms(raw: str | None) -> list[str]:
    """Return normalized substring filters from a comma/newline separated value."""

    if not raw:
        return []
    out: list[str] = []
    for chunk in str(raw).replace("\n", ",").split(","):
        clean = " ".join(str(chunk).strip().lower().replace("_", " ").split())
        if clean:
            out.append(clean)
    return out


def _template_search_blob(template: dict[str, Any]) -> str:
    """Return one normalized text blob for inclusion/exclusion matching."""

    pieces = [
        str(template.get("name") or ""),
        str(template.get("groups") or ""),
        str(template.get("notes") or ""),
        str(template.get("url") or ""),
        str(template.get("last_caption") or ""),
    ]
    return " ".join(
        " ".join(piece.lower().replace("_", " ").split()) for piece in pieces
    )


def _parse_template_timestamp(raw: Any) -> datetime | None:
    """Parse the template timestamp format used throughout Glimpser."""

    text = str(raw or "").strip()
    if not text:
        return None
    try:
        return datetime.strptime(text, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def _normalize_high_fidelity_mode(raw: Any) -> str:
    """Return the supported per-camera high-fidelity mode."""

    value = str(raw or "auto").strip().lower()
    if value not in {"auto", "include", "exclude"}:
        return "auto"
    return value


def _parse_high_fidelity_rank(raw: Any) -> int:
    """Return the bounded per-camera high-fidelity priority."""

    try:
        return max(0, min(100, int(float(raw or 0))))
    except (TypeError, ValueError):
        return 0


def _latest_template_image_path(name: str) -> str | None:
    """Return the most recent PNG path for ``name`` if one exists."""

    from app import routes

    clean_name = routes.validate_template_name(name)
    if clean_name is None:
        return None
    path = routes.os.path.join(
        routes.os.path.dirname(routes.os.path.abspath(__file__)),
        "..",
        routes.SCREENSHOT_DIRECTORY,
        clean_name,
    )
    latest_link = routes.os.path.join(path, "latest_camera.png")
    if routes.os.path.exists(latest_link):
        return latest_link
    try:
        entries = routes.os.listdir(path)
    except FileNotFoundError:
        return None
    pngs: list[tuple[float, str]] = []
    for entry in entries:
        if not entry.endswith(".png") or entry.endswith(".tmp.png"):
            continue
        full = routes.os.path.join(path, entry)
        if not routes.os.path.isfile(full):
            continue
        try:
            mtime = routes.os.path.getmtime(full)
        except OSError:
            continue
        pngs.append((mtime, full))
    if not pngs:
        return None
    pngs.sort(key=lambda row: row[0], reverse=True)
    return pngs[0][1]


def _high_fidelity_candidates(
    *,
    group: str | None,
    include_terms: list[str],
    exclude_terms: list[str],
    max_age_s: int,
    limit: int,
    caption_guard: bool,
) -> list[dict[str, Any]]:
    """Return curated screenshot candidates for the TV-style feed.

    The endpoint is meant to be slow and presentable. We therefore only select
    templates that are fresh, not currently failed, and whose last captions do
    not look like broken/partial captures.
    """

    from app import routes

    now = routes.datetime.utcnow()
    selected: list[dict[str, Any]] = []
    for name, template in routes.template_manager.get_templates().items():
        clean_name = routes.validate_template_name(name)
        if clean_name is None:
            continue
        if bool(template.get("capture_failed")):
            continue
        # Prefer the explicit privacy toggle, but keep the older metadata
        # conventions as a fallback for existing templates.
        if bool(template.get("private_camera")):
            continue
        manual_mode = _normalize_high_fidelity_mode(template.get("high_fidelity_mode"))
        if manual_mode == "exclude":
            continue
        manual_rank = _parse_high_fidelity_rank(template.get("high_fidelity_rank"))
        groups = [
            g.strip() for g in str(template.get("groups") or "").split(",") if g.strip()
        ]
        if group and group not in groups:
            continue

        blob = _template_search_blob(template)
        if include_terms and not any(term in blob for term in include_terms):
            continue
        query_excludes = exclude_terms[len(_HIGH_FIDELITY_DEFAULT_EXCLUDE) :]
        if any(term in blob for term in query_excludes):
            continue
        # Explicit includes can override the default metadata heuristics, but
        # operator-supplied query excludes should still win.
        if manual_mode != "include" and any(term in blob for term in exclude_terms):
            continue

        if caption_guard:
            caption_blob = " ".join(
                str(template.get("last_caption") or "").lower().split()
            )
            if any(term in caption_blob for term in _HIGH_FIDELITY_BAD_CAPTION_TOKENS):
                continue

        ts = _parse_template_timestamp(template.get("last_screenshot_time"))
        age_s = int((now - ts).total_seconds()) if ts else 10**9
        if age_s > max_age_s:
            continue

        image_path = _latest_template_image_path(clean_name)
        if not image_path or not routes.os.path.exists(image_path):
            continue
        if not routes.screenshots._is_valid_png(image_path):
            continue

        try:
            with routes.Image.open(image_path) as img:
                img = img.convert("RGB")
                width, height = img.size
                # Reject obviously broken crops/placeholders before TV rotation.
                if width < 320 or height < 180:
                    continue
                if routes.screenshots.is_mostly_blank(img):
                    continue
        except Exception:
            continue

        selected.append(
            {
                "name": clean_name,
                "groups": groups,
                "notes": str(template.get("notes") or ""),
                "last_caption": str(template.get("last_caption") or ""),
                "last_screenshot_time": str(template.get("last_screenshot_time") or ""),
                "freshness_s": age_s,
                "high_fidelity_mode": manual_mode,
                "high_fidelity_rank": manual_rank,
                "image_path": image_path,
            }
        )

    # Prefer explicit includes first, then operator rank, then freshness.
    selected.sort(
        key=lambda row: (
            0 if row["high_fidelity_mode"] == "include" else 1,
            -row["high_fidelity_rank"],
            row["freshness_s"],
            row["name"].lower(),
        )
    )
    return selected[:limit]


def _encode_high_fidelity_frame(image) -> bytes:
    """Encode a TV-feed frame as JPEG with stable settings."""

    buf = io.BytesIO()
    image.save(buf, format="JPEG", quality=90, optimize=True)
    return buf.getvalue()


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
        user_agent = routes.request.headers.get("User-Agent", "")
        routes.logging.info(
            "stream.mjpg connect ip=%s group=%s camera=%s ua=%s",
            routes.request.remote_addr,
            group,
            camera,
            user_agent,
        )
        if (not group) and (not camera) and "autocamera" in user_agent.lower():
            return redirect(
                "/high_fidelity_stream.mjpg"
                "?hold_s=12&transition_ms=1400&limit=36&max_age_s=7200"
                "&exclude=showroom,private,safe",
                code=302,
            )
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

    @bp.route("/high_fidelity.json", methods=["GET"])
    @routes.login_required
    def high_fidelity_json() -> Response:
        """Return curated TV-style candidates for autocamera or operator tools."""

        group = routes.request.args.get("group")
        if group == "all":
            group = None
        include_terms = _parse_high_fidelity_terms(routes.request.args.get("include"))
        exclude_terms = list(_HIGH_FIDELITY_DEFAULT_EXCLUDE)
        exclude_terms.extend(
            _parse_high_fidelity_terms(routes.request.args.get("exclude"))
        )
        max_age_s = max(
            30,
            min(
                86400,
                int(float(routes.request.args.get("max_age_s") or 7200)),
            ),
        )
        limit = max(
            1,
            min(
                100,
                int(float(routes.request.args.get("limit") or 24)),
            ),
        )
        hold_s = max(
            2.0,
            min(
                120.0,
                float(routes.request.args.get("hold_s") or 12),
            ),
        )
        transition_ms = max(
            0,
            min(
                10000,
                int(float(routes.request.args.get("transition_ms") or 1400)),
            ),
        )
        caption_guard = str(
            routes.request.args.get("caption_guard", "true")
        ).strip().lower() not in {"0", "false", "off", "no"}

        selected = _high_fidelity_candidates(
            group=group,
            include_terms=include_terms,
            exclude_terms=exclude_terms,
            max_age_s=max_age_s,
            limit=limit,
            caption_guard=caption_guard,
        )
        payload = {
            "profile": "high_fidelity",
            "group": group or "all",
            "hold_s": hold_s,
            "transition_ms": transition_ms,
            "count": len(selected),
            "items": [
                {
                    "name": row["name"],
                    "groups": row["groups"],
                    "primary_group": (
                        row["groups"][0] if row["groups"] else "highlights"
                    ),
                    "notes": row["notes"],
                    "last_caption": row["last_caption"],
                    "last_screenshot_time": row["last_screenshot_time"],
                    "freshness_s": row["freshness_s"],
                    "high_fidelity_mode": row["high_fidelity_mode"],
                    "high_fidelity_rank": row["high_fidelity_rank"],
                    "image_url": routes.url_for(
                        "stream.stream_png", camera=row["name"], _external=True
                    ),
                    "video_url": routes.url_for(
                        "assets.serve_video",
                        template_name=row["name"],
                        _external=True,
                    ),
                    "group_url": (
                        routes.url_for(
                            "views.group_page",
                            group_name=row["groups"][0] if row["groups"] else "all",
                            _external=True,
                        )
                        if row["groups"]
                        else routes.url_for("views.index", _external=True)
                    ),
                    "live_url": routes.url_for(
                        "ui.live", camera=row["name"], _external=True
                    ),
                    "template_url": routes.url_for(
                        "ui.template_details",
                        template_name=row["name"],
                        _external=True,
                    ),
                }
                for row in selected
            ],
        }
        return jsonify(payload)

    @bp.route("/high_fidelity_stream.mjpg", methods=["GET"])
    @bp.route("/high_fidelity.mjpg", methods=["GET"])
    @routes.login_required
    def high_fidelity_mjpg() -> Response:
        """Serve a slow, curated MJPEG wall with gentle cross-fades.

        This is the "TV" endpoint. It intentionally trades cadence for better
        presentation quality and allows autocamera to tweak behavior via query
        params rather than hardcoding another source list.
        """

        group = routes.request.args.get("group")
        if group == "all":
            group = None
        include_terms = _parse_high_fidelity_terms(routes.request.args.get("include"))
        exclude_terms = list(_HIGH_FIDELITY_DEFAULT_EXCLUDE)
        exclude_terms.extend(
            _parse_high_fidelity_terms(routes.request.args.get("exclude"))
        )
        max_age_s = max(
            30,
            min(
                86400,
                int(float(routes.request.args.get("max_age_s") or 7200)),
            ),
        )
        limit = max(
            1,
            min(
                100,
                int(float(routes.request.args.get("limit") or 24)),
            ),
        )
        hold_s = max(
            2.0,
            min(
                120.0,
                float(routes.request.args.get("hold_s") or 12),
            ),
        )
        transition_ms = max(
            0,
            min(
                10000,
                int(float(routes.request.args.get("transition_ms") or 1400)),
            ),
        )
        transition_fps = max(
            1,
            min(
                24,
                int(float(routes.request.args.get("transition_fps") or 6)),
            ),
        )
        caption_guard = str(
            routes.request.args.get("caption_guard", "true")
        ).strip().lower() not in {"0", "false", "off", "no"}

        def generate_high_fidelity():
            boundary = b"frame"
            placeholder_frame = None

            def get_placeholder_frame() -> bytes:
                nonlocal placeholder_frame
                if placeholder_frame is None:
                    placeholder = routes._placeholder_screenshot()
                    with routes.Image.open(placeholder) as img:
                        placeholder_frame = _encode_high_fidelity_frame(
                            routes.resize_and_pad(img.convert("RGB"), (1280, 720))
                        )
                return placeholder_frame

            # Emit an immediate frame so slow candidate selection does not make
            # MJPEG clients treat the endpoint as stalled.
            yield b"--" + boundary + b"\r\n"
            yield (
                b"Content-Type: image/jpeg\r\n\r\n"
                + get_placeholder_frame()
                + b"\r\n\r\n"
            )
            while True:
                cache_key = (
                    group,
                    tuple(include_terms),
                    tuple(exclude_terms),
                    max_age_s,
                    limit,
                    caption_guard,
                )
                now = routes.time.time()
                cached = _HIGH_FIDELITY_CANDIDATE_CACHE.get(cache_key)
                if cached and (now - cached[0]) <= _HIGH_FIDELITY_CANDIDATE_CACHE_TTL_S:
                    selected = [dict(row) for row in cached[1]]
                else:
                    selected = _high_fidelity_candidates(
                        group=group,
                        include_terms=include_terms,
                        exclude_terms=exclude_terms,
                        max_age_s=max_age_s,
                        limit=limit,
                        caption_guard=caption_guard,
                    )
                    _HIGH_FIDELITY_CANDIDATE_CACHE[cache_key] = (
                        routes.time.time(),
                        [dict(row) for row in selected],
                    )
                if not selected:
                    yield b"--" + boundary + b"\r\n"
                    yield (
                        b"Content-Type: image/jpeg\r\n\r\n"
                        + get_placeholder_frame()
                        + b"\r\n\r\n"
                    )
                    routes.time.sleep(2.0)
                    continue

                prepared = []
                for row in selected:
                    try:
                        with routes.Image.open(row["image_path"]) as img:
                            prepared.append(
                                {
                                    **row,
                                    "image": routes.resize_and_pad(
                                        img.convert("RGB"), (1280, 720)
                                    ),
                                }
                            )
                    except Exception:
                        continue
                if not prepared:
                    routes.time.sleep(1.0)
                    continue

                for idx, current in enumerate(prepared):
                    current_frame = _encode_high_fidelity_frame(current["image"])
                    still_frames = max(1, int(round(hold_s)))
                    for _ in range(still_frames):
                        yield b"--" + boundary + b"\r\n"
                        yield (
                            b"Content-Type: image/jpeg\r\n\r\n"
                            + current_frame
                            + b"\r\n\r\n"
                        )
                        routes.time.sleep(max(0.25, hold_s / still_frames))

                    if transition_ms <= 0 or len(prepared) < 2:
                        continue

                    nxt = prepared[(idx + 1) % len(prepared)]
                    steps = max(
                        1,
                        int(round((transition_ms / 1000.0) * transition_fps)),
                    )
                    # Blend on the server so downstream operators can treat this
                    # as one polished source without reimplementing transitions.
                    for step in range(1, steps + 1):
                        alpha = step / float(steps + 1)
                        blended = routes.Image.blend(
                            current["image"], nxt["image"], alpha
                        )
                        frame = _encode_high_fidelity_frame(blended)
                        yield b"--" + boundary + b"\r\n"
                        yield (
                            b"Content-Type: image/jpeg\r\n\r\n" + frame + b"\r\n\r\n"
                        )
                        routes.time.sleep(1.0 / transition_fps)

        return Response(
            generate_high_fidelity(),
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
        routes.logging.info(
            "fast_stream.mjpg connect ip=%s camera=%s ua=%s",
            routes.request.remote_addr,
            camera,
            routes.request.headers.get("User-Agent", ""),
        )
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

    @bp.route("/warm_live")
    @routes.login_required
    def warm_live() -> Response:
        """Pre-warm a camera live pipeline for fast time-to-first-frame."""

        camera = routes.request.args.get("camera")
        if not camera:
            routes.abort(400, "camera parameter required")
        details = routes.template_manager.get_template(camera)
        if not details:
            routes.abort(404)

        profile = (routes.request.args.get("profile") or "sub").strip().lower()
        if profile not in {"main", "sub", "auto"}:
            profile = "sub"

        quality = (routes.request.args.get("quality") or "first").strip().lower()
        if quality not in {"first", "low", "high", "auto"}:
            quality = "first"

        stream_url = routes.resolve_live_stream_url(details, profile=profile)
        url = stream_url or details.get("url")
        if not url:
            routes.abort(404)

        host_key = routes.live_host_key(str(url))
        now = routes.time.time()
        skip_ok_s = int(getattr(routes.config, "LIVE_PREFLIGHT_SKIP_OK_SECONDS", 20))

        url_caps = routes.live_caps.get(str(url))
        host_caps = routes.live_host_caps.get(host_key) if host_key else None
        recent_ok = bool(
            url_caps.last_ok_ts and (now - float(url_caps.last_ok_ts)) <= skip_ok_s
        )
        host_recent_ok = bool(
            host_caps
            and host_caps.last_ok_ts
            and (now - float(host_caps.last_ok_ts)) <= skip_ok_s
        )

        # Avoid stampeding: at most one warm request per host at a time (per worker).
        warm_token = None
        if host_key:
            warm_token = routes.live_limits.try_acquire(
                host_key, kind="warm_live", limit=1, timeout=0.0
            )
            if warm_token is None:
                return Response(status=204)

        try:
            if not (recent_ok or host_recent_ok):
                if host_key and not routes.live_host_caps.should_attempt(host_key):
                    routes.live_caps.record_failure(str(url), reason="host_avoid")
                    return Response(status=204)

                ok_pre, _pre_info = routes.preflight_live_url(str(url))
                if not ok_pre:
                    if host_key:
                        routes.live_host_caps.record_failure(
                            host_key, reason="preflight"
                        )
                    routes.live_caps.record_failure(str(url), reason="preflight")
                    return Response(status=204)
        finally:
            if warm_token:
                warm_token.release()

        width = None
        fps = None
        if quality == "first":
            width = min(routes.config.LIVE_RTSP_WIDTH, 360)
            fps = min(routes.config.LIVE_RTSP_FPS, 2)
        elif quality == "low":
            width = min(routes.config.LIVE_RTSP_WIDTH, 480)
            fps = min(routes.config.LIVE_RTSP_FPS, 3)
        elif quality == "kiosk":
            width = min(routes.config.LIVE_RTSP_WIDTH, 960)
            fps = min(routes.config.LIVE_RTSP_FPS, 3)
        elif quality == "high":
            width = max(routes.config.LIVE_RTSP_WIDTH, 1280)
            width = min(width, 1920)
            fps = max(routes.config.LIVE_RTSP_FPS, 10)
            fps = min(fps, 15)

        routes.warm_live(url, width=width, fps=fps)
        return Response(status=204)

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
        if quality not in {"auto", "low", "high", "first", "kiosk"}:
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

        host_key = routes.live_host_key(str(url))
        now = routes.time.time()
        skip_ok_s = int(getattr(routes.config, "LIVE_PREFLIGHT_SKIP_OK_SECONDS", 20))

        url_caps = routes.live_caps.get(str(url))
        host_caps = routes.live_host_caps.get(host_key) if host_key else None
        recent_ok = bool(
            url_caps.last_ok_ts and (now - float(url_caps.last_ok_ts)) <= skip_ok_s
        )
        host_recent_ok = bool(
            host_caps
            and host_caps.last_ok_ts
            and (now - float(host_caps.last_ok_ts)) <= skip_ok_s
        )

        # Best-effort per-host concurrency limit (per worker).
        token = None
        if host_key:
            max_streams = int(getattr(routes.config, "LIVE_HOST_MAX_STREAMS", 2) or 0)
            if max_streams > 0:
                token = routes.live_limits.wait_acquire(
                    host_key,
                    kind="live_video",
                    limit=max_streams,
                    max_wait_s=0.5,
                )
                if token is None:
                    resp = Response(status=503)
                    resp.headers["Retry-After"] = "2"
                    return resp

        # Cheap preflight + circuit breaker to avoid stampeding degraded LAN hosts.
        # Skip when we have a very recent proven-good stream.
        if not (recent_ok or host_recent_ok):
            if host_key and not routes.live_host_caps.should_attempt(host_key):
                routes.live_caps.record_failure(str(url), reason="host_avoid")
                resp = Response(status=503)
                resp.headers["Retry-After"] = "2"
                if token:
                    token.release()
                return resp

            ok_pre, pre_info = routes.preflight_live_url(str(url))
            if not ok_pre:
                if host_key:
                    routes.live_host_caps.record_failure(
                        host_key, reason=str(pre_info.get("reason") or "")
                    )
                routes.live_caps.record_failure(str(url), reason="preflight")
                resp = Response(status=503)
                resp.headers["Retry-After"] = "2"
                if token:
                    token.release()
                return resp

        width = None
        fps = None
        if quality == "first":
            width = min(routes.config.LIVE_RTSP_WIDTH, 360)
            fps = min(routes.config.LIVE_RTSP_FPS, 2)
        elif quality == "low":
            width = min(routes.config.LIVE_RTSP_WIDTH, 480)
            fps = min(routes.config.LIVE_RTSP_FPS, 3)
        elif quality == "kiosk":
            width = min(routes.config.LIVE_RTSP_WIDTH, 960)
            fps = min(routes.config.LIVE_RTSP_FPS, 3)
        elif quality == "high":
            width = max(routes.config.LIVE_RTSP_WIDTH, 1280)
            width = min(width, 1920)
            fps = max(routes.config.LIVE_RTSP_FPS, 10)
            fps = min(fps, 15)

        use_warm = (
            quality in {"first", "low", "high", "kiosk"}
            and isinstance(url, str)
            and url.lower().startswith(("rtsp://", "rtsps://"))
        )

        if use_warm:
            inner = routes.generate_warm_live_stream(url, width=width, fps=fps)
        else:
            inner = routes.generate_live_stream(
                url,
                width=width,
                fps=fps,
                max_no_output_seconds=8.0,
                max_no_output_failures=2,
            )

        def limited_gen():
            try:
                yield from inner
            finally:
                if token:
                    token.release()

        resp = Response(
            routes.stream_with_context(limited_gen()),
            mimetype="video/mp4",
        )
        resp.headers["X-Live-Source"] = "stream" if stream_url else "fallback"
        resp.headers["X-Live-Profile"] = profile
        resp.headers["X-Live-Quality"] = quality
        resp.headers["X-Live-Warm"] = "1" if use_warm else "0"
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
