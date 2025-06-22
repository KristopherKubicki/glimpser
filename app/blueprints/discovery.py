from __future__ import annotations

import csv
import io
import json
import queue
from ipaddress import ip_network
from threading import Thread

from flask import (
    Blueprint,
    Response,
    jsonify,
    render_template,
    request,
    stream_with_context,
)


def create_blueprint() -> Blueprint:
    """Create and return the camera discovery blueprint."""

    import app.routes as routes

    bp = Blueprint("discovery", __name__)

    @bp.route("/discover", methods=["GET"])
    @routes.login_required
    def discover_cameras_route() -> Response:
        """Render the camera discovery page."""

        templates = routes.template_manager.get_templates()
        existing_urls = {t.get("url"): n for n, t in templates.items() if t.get("url")}
        object_tokens = ["person", "car", "dog", "cat", "truck", "bus", "bicycle"]
        return routes.render_template(
            "discover.html",
            cameras=[],
            existing_urls=existing_urls,
            object_tokens=object_tokens,
            clip_model=routes.CLIP_MODEL_NAME,
            clip_gpu=routes.clip_gpu_available(),
            page_title="Discover Cameras",
        )

    @bp.route("/discover/scan", methods=["POST"])
    @routes.login_required
    def discover_cameras_scan() -> Response:
        """Return a list of discovered cameras for the given subnet."""

        cidr = request.form.get("cidr") if request.form else request.args.get("cidr")
        nets = None
        if cidr and cidr.lower() == "internet":
            from app.utils.internet_cameras import INTERNET_CAMERAS

            return jsonify(INTERNET_CAMERAS)
        if cidr:
            try:
                nets = [ip_network(cidr, strict=False)]
            except ValueError:
                pass
        cameras = routes.camera_discovery.discover_cameras(subnets=nets)
        return jsonify(cameras)

    @bp.route("/discover/scan_stream")
    @routes.login_required
    def discover_cameras_scan_stream() -> Response:
        """Stream discovery results as Server-Sent Events."""

        def generate():
            cidr = request.args.get("cidr")
            nets = None
            if cidr and cidr.lower() == "internet":
                from app.utils.internet_cameras import INTERNET_CAMERAS

                yield (
                    "data: "
                    + json.dumps(
                        {"total": 1, "subnets": ["internet"], "stages": ["internet"]}
                    )
                    + "\n\n"
                )
                yield (
                    "data: "
                    + json.dumps(
                        {
                            "stage": "internet",
                            "count": len(INTERNET_CAMERAS),
                            "cameras": INTERNET_CAMERAS,
                            "progress": 100,
                            "eta": 0,
                        }
                    )
                    + "\n\n"
                )
                yield 'data: {"done": true}\n\n'
                return
            if cidr:
                try:
                    nets = [ip_network(cidr, strict=False)]
                except ValueError:
                    pass

            stages = routes.camera_discovery.get_discovery_stages()

            q: queue.Queue[dict[str, object]] = queue.Queue()
            q.put(
                {
                    "total": len(stages),
                    "subnets": [
                        str(n)
                        for n in (nets or routes.camera_discovery._local_subnets())
                    ],
                    "stages": stages,
                }
            )

            sent: set[tuple[str, str, int]] = set()

            def progress(
                stage: str,
                count: int,
                new_cams: list[dict[str, object]],
                pct: int,
                eta: int,
            ) -> None:
                fresh = []
                for cam in new_cams:
                    key = (cam.get("ip"), cam.get("protocol"), cam.get("port"))
                    if key not in sent:
                        sent.add(key)
                        fresh.append(cam)
                q.put(
                    {
                        "stage": stage,
                        "count": count,
                        "cameras": fresh,
                        "progress": pct,
                        "eta": eta,
                    }
                )

            def run() -> None:
                try:
                    routes.camera_discovery.discover_cameras(
                        progress_callback=progress, subnets=nets
                    )
                except Exception as e:  # pragma: no cover - network
                    routes.logging.exception("discovery scan failed: %s", e)
                    q.put({"error": str(e)})
                finally:
                    q.put({"done": True})

            thread = Thread(target=run, daemon=True)
            thread.start()

            while True:
                msg = q.get()
                yield f"data: {json.dumps(msg)}\n\n"
                if msg.get("done"):
                    break

        return Response(stream_with_context(generate()), mimetype="text/event-stream")

    @bp.route("/discover/add", methods=["POST"])
    @routes.login_required
    def add_discovered_camera() -> Response:
        """Save a discovered camera as a new template."""

        data = request.form if request.form else request.get_json(force=True)
        name = data.get("name") or data.get("ip")
        protocol = data.get("protocol", "rtsp")
        port = int(data.get("port", 554))
        url = data.get("url") or f"{protocol}://{data.get('ip')}:{port}"
        template = {
            "name": name,
            "url": url,
            "frequency": data.get("frequency", 30),
            "timeout": data.get("timeout", 10),
        }
        routes.template_manager.save_template(name, template)
        return jsonify({"status": "success"})

    @bp.route("/templates/test_url")
    @routes.login_required
    def test_template_url() -> Response:
        """Return JSON indicating whether the given URL is reachable."""

        url = request.args.get("url") or ""
        url = routes.validators.validate_url(url)
        if not url:
            return jsonify({"ok": False, "error": "invalid"}), 400

        try:
            resp = routes.requests.head(url, timeout=5)
            ok = resp.status_code < 400
        except Exception as exc:  # pragma: no cover - network
            routes.logging.warning("url check failed: %s", exc)
            return jsonify({"ok": False, "error": "unreachable"}), 400

        return jsonify({"ok": ok, "status": resp.status_code})

    @bp.route("/discover/export", methods=["POST"])
    @routes.login_required
    def export_discovery_results() -> Response:
        """Export scanned camera results as JSON or CSV."""

        fmt = request.args.get("format", "json")
        cameras = request.get_json(force=True)
        if not isinstance(cameras, list):
            cameras = cameras.get("cameras", []) if isinstance(cameras, dict) else []
        if fmt == "csv":
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(
                ["ip", "protocol", "port", "mac", "manufacturer", "firmware"]
            )
            for cam in cameras:
                info = cam.get("info", {})
                writer.writerow(
                    [
                        cam.get("ip"),
                        cam.get("protocol"),
                        cam.get("port"),
                        info.get("mac"),
                        info.get("manufacturer"),
                        info.get("firmware"),
                    ]
                )
            output.seek(0)
            return Response(
                output.getvalue(),
                mimetype="text/csv",
                headers={"Content-Disposition": "attachment;filename=discovery.csv"},
            )
        return Response(
            json.dumps(cameras, indent=2),
            mimetype="application/json",
            headers={"Content-Disposition": "attachment;filename=discovery.json"},
        )

    return bp
