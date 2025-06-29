from __future__ import annotations

import os

from flask import Blueprint, send_from_directory


def create_blueprint() -> Blueprint:
    """Create and return the documentation blueprint."""

    from app import routes

    bp = Blueprint("docs", __name__)

    @bp.route("/docs/<string:filename>", endpoint="docs_file")
    @routes.login_required
    def docs_file(filename: str):
        """Serve Markdown documentation files from the repository."""
        if not routes.allowed_filename(filename):
            routes.abort(404)
        docs_path = os.path.join(
            os.path.dirname(os.path.join(__file__)), "..", routes.DOCS_DIRECTORY
        )
        full_path = os.path.join(docs_path, filename)
        if not os.path.exists(full_path):
            routes.abort(404)
        return send_from_directory(docs_path, filename)

    return bp
