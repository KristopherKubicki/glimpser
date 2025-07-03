from __future__ import annotations

from flask import Blueprint, redirect, url_for


def create_blueprint() -> Blueprint:
    """Return a blueprint redirecting timeline requests."""

    from app import routes

    bp = Blueprint("timeline", __name__)

    @bp.route("/timeline", endpoint="timeline")
    @routes.login_required
    def timeline():
        """Redirect to the caption history view."""

        return redirect(url_for("ui.captions", tab="history-tab"))

    return bp
