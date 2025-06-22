from __future__ import annotations

import json
import time
from flask import Blueprint, Response, jsonify, request, stream_with_context


def create_blueprint() -> Blueprint:
    """Create and return the logs blueprint."""

    import app.routes as routes

    bp = Blueprint("logs", __name__)

    @bp.route("/logs")
    @routes.login_required
    def logs():
        """Render the logs page."""
        return routes.render_template("logs.html", page_title="Logs")

    @bp.route("/cost_summary")
    @routes.login_required
    def cost_summary_page():
        """Render a summary of LLM costs."""
        templates = routes.template_manager.get_templates()
        costs = {
            name: routes.template_manager.get_llm_cost_estimate(name)
            for name in templates
        }
        start_time = int(
            routes.scheduling.system_metrics.get("start_time", time.time())
        )
        return routes.render_template(
            "cost_summary.html",
            costs=costs,
            start_time=start_time,
            page_title="LLM Cost Summary",
        )

    @bp.route("/api/llm_cost_summary")
    @routes.login_required
    def api_llm_cost_summary():
        """Return LLM cost data as JSON."""
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

    @bp.route("/api/camera_log_summary/<string:template_name>")
    @routes.login_required
    def api_camera_log_summary(template_name: routes.TemplateName):
        """Return summarized logs for ``template_name``."""
        template_name = routes.validate_template_name(str(template_name))
        if template_name is None:
            routes.abort(404)
        summary = routes.scheduling.get_or_generate_camera_log_summary(template_name)
        if summary is None:
            return "", 204
        return jsonify({"summary": summary})

    @bp.route("/stream_logs")
    @routes.login_required
    def stream_logs() -> Response:
        """Stream recent logs via Server-Sent Events."""
        level = request.args.get("level")
        source = request.args.get("source")
        start_date = request.args.get("start_date")
        end_date = request.args.get("end_date")
        search = request.args.get("search")

        user_id = routes.session.get("user_id", 0)
        combo = (int(user_id), level or "", search or "")
        if combo in routes.active_log_streams:
            return Response(
                "event: duplicate\ndata: {}\n\n",
                mimetype="text/event-stream",
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

        return Response(stream_with_context(generate()), mimetype="text/event-stream")

    return bp
