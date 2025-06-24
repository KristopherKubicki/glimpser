from __future__ import annotations

from flask import Blueprint


def _decorate(func):
    """Reapply the current login_required decorator."""
    import app.routes as routes

    base = getattr(func, "__wrapped__", func)
    return routes.login_required(base)


def create_blueprint() -> Blueprint:
    """Create and return the UI blueprint."""

    import app.routes as routes

    bp = Blueprint("ui", __name__)

    bp.add_url_rule(
        "/danger",
        view_func=_decorate(routes.danger_mode),
        methods=["GET", "POST"],
        endpoint="danger_mode",
    )
    bp.add_url_rule("/stream", view_func=_decorate(routes.stream), endpoint="stream")
    bp.add_url_rule(
        "/groups", view_func=_decorate(routes.get_groups), endpoint="get_groups"
    )
    bp.add_url_rule(
        "/captions", view_func=_decorate(routes.captions), endpoint="captions"
    )
    bp.add_url_rule(
        "/download_captions_tsv",
        view_func=_decorate(routes.download_captions_tsv),
        endpoint="download_captions_tsv",
    )
    bp.add_url_rule(
        "/upload_captions_tsv",
        view_func=_decorate(routes.upload_captions_tsv),
        methods=["POST"],
        endpoint="upload_captions_tsv",
    )
    bp.add_url_rule(
        "/captions_chat",
        view_func=_decorate(routes.captions_chat),
        methods=["POST"],
        endpoint="captions_chat",
    )
    bp.add_url_rule("/live", view_func=_decorate(routes.live), endpoint="live")
    bp.add_url_rule(
        "/clock", view_func=_decorate(routes.clock_page), endpoint="clock_page"
    )
    bp.add_url_rule(
        "/latest_frame/<string:template_name>",
        view_func=_decorate(routes.latest_frame),
        endpoint="latest_frame",
    )
    bp.add_url_rule(
        "/upload_nav_icon",
        view_func=_decorate(routes.upload_nav_icon),
        methods=["POST"],
        endpoint="upload_nav_icon",
    )
    bp.add_url_rule(
        "/templates",
        view_func=_decorate(routes.manage_templates),
        methods=["GET", "POST", "DELETE"],
        endpoint="manage_templates",
    )
    bp.add_url_rule(
        "/templates/<string:template_name>",
        view_func=_decorate(routes.template_details),
        endpoint="template_details",
    )
    bp.add_url_rule(
        "/generate_prompt/<string:template_name>",
        view_func=_decorate(routes.generate_prompt_route),
        methods=["POST"],
        endpoint="generate_prompt_route",
    )
    bp.add_url_rule(
        "/suggest_fix/<string:template_name>",
        view_func=_decorate(routes.suggest_fix_route),
        methods=["POST"],
        endpoint="suggest_fix_route",
    )
    bp.add_url_rule(
        "/camera_diagnostics/<string:template_name>",
        view_func=_decorate(routes.camera_diagnostics),
        endpoint="camera_diagnostics",
    )
    bp.add_url_rule(
        "/settings",
        view_func=_decorate(routes.settings),
        methods=["GET", "POST"],
        endpoint="settings",
    )
    bp.add_url_rule(
        "/update_template/<string:template_name>",
        view_func=_decorate(routes.update_template),
        methods=["POST"],
        endpoint="update_template",
    )
    bp.add_url_rule("/status", view_func=_decorate(routes.status), endpoint="status")
    bp.add_url_rule("/logs", view_func=_decorate(routes.logs), endpoint="logs")
    bp.add_url_rule(
        "/cost_summary",
        view_func=_decorate(routes.cost_summary_page),
        endpoint="cost_summary_page",
    )
    bp.add_url_rule(
        "/api/llm_cost_summary",
        view_func=_decorate(routes.api_llm_cost_summary),
        endpoint="api_llm_cost_summary",
    )
    bp.add_url_rule(
        "/api/camera_log_summary/<string:template_name>",
        view_func=_decorate(routes.api_camera_log_summary),
        endpoint="api_camera_log_summary",
    )
    bp.add_url_rule(
        "/stream_logs",
        view_func=_decorate(routes.stream_logs),
        endpoint="stream_logs",
    )
    bp.add_url_rule(
        "/search_suggestions",
        view_func=_decorate(routes.search_suggestions),
        endpoint="search_suggestions",
    )

    return bp
