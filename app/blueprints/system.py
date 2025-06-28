from __future__ import annotations

from flask import Blueprint, jsonify, redirect, url_for


def create_blueprint() -> Blueprint:
    """Create and return the system management blueprint."""

    from app import routes

    bp = Blueprint("system", __name__)

    @bp.route("/system_metrics")
    def system_metrics():
        return redirect(url_for("health_check"))

    @bp.route("/toggle_scheduler", methods=["POST"])
    @routes.login_required
    @routes.profile_route("/toggle_scheduler")
    def toggle_scheduler():
        try:
            if routes.scheduling.scheduler.running:
                routes.scheduling.scheduler.shutdown(wait=True)
                return jsonify({"status": "stopped"})
            routes.scheduling.scheduler.start()
            with routes.current_app.app_context():
                routes.scheduling.scheduler.remove_all_jobs()
                routes.scheduling.schedule_crawlers()
                routes.scheduling.schedule_summarization()
            return jsonify({"status": "running"})
        except Exception as e:  # pragma: no cover - unexpected errors
            return jsonify({"status": "error", "message": str(e)}), 500

    @bp.route("/scheduler_status")
    @routes.login_required
    @routes.profile_route("/scheduler_status")
    def scheduler_status():
        return jsonify(
            {
                "status": (
                    "running" if routes.scheduling.scheduler.running else "stopped"
                )
            }
        )

    @bp.route("/profiling")
    @routes.login_required
    def profiling_data():
        return jsonify(routes.get_latency_stats())

    return bp
