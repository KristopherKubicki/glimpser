from __future__ import annotations

from flask import Blueprint, jsonify


def create_blueprint() -> Blueprint:
    """Create and return the API blueprint."""

    import app.routes as routes

    bp = Blueprint("api", __name__)

    @bp.route("/api/discover")
    @routes.profile_route("/api/discover")
    def api_discover():
        """Return metadata about available API endpoints."""

        api_info = {
            "version": "1.0",
            "endpoints": [
                {
                    "path": "/health",
                    "method": "GET",
                    "description": "Check the health status of the API",
                    "authentication_required": True,
                },
                {
                    "path": "/danger_status",
                    "method": "GET",
                    "description": "Check if Danger mode is ready",
                    "authentication_required": True,
                },
                {
                    "path": "/captions_status",
                    "method": "GET",
                    "description": "Get the most recent caption and timestamp",
                    "authentication_required": True,
                },
                {
                    "path": "/discovery_status",
                    "method": "GET",
                    "description": "Check background discovery status",
                    "authentication_required": True,
                },
                {
                    "path": "/api/discover",
                    "method": "GET",
                    "description": "Get information about available API endpoints",
                    "authentication_required": False,
                },
                {
                    "path": "/login",
                    "method": "GET, POST",
                    "description": "User login endpoint",
                    "authentication_required": False,
                },
                {
                    "path": "/logout",
                    "method": "GET",
                    "description": "User logout endpoint",
                    "authentication_required": True,
                },
                {
                    "path": "/",
                    "method": "GET",
                    "description": "Main index page",
                    "authentication_required": True,
                },
                {
                    "path": "/templates",
                    "method": "GET, POST, DELETE",
                    "description": "Manage templates",
                    "authentication_required": True,
                },
                {
                    "path": "/settings",
                    "method": "GET, POST",
                    "description": "Manage application settings",
                    "authentication_required": True,
                },
            ],
        }
        return jsonify(api_info), 200

    return bp
