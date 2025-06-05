from flask import Blueprint, jsonify, request
from . import profile_route, login_required

bp = Blueprint("api", __name__)


@bp.route("/api/discover")
@profile_route("/api/discover")
def api_discover():
    api_info = {
        "version": "1.0",
        "endpoints": [
            {
                "path": "/health",
                "method": "GET",
                "description": "Check the health status of the API",
                "authentication_required": False,
            },
        ],
    }
    return jsonify(api_info), 200


@bp.route("/mcp/tools")
@login_required
def mcp_tools():
    from app.utils import mcp

    tools = mcp.list_tools_sync()
    return jsonify(tools)


@bp.route("/mcp/tool/<string:name>", methods=["POST"])
@login_required
def mcp_call_tool(name):
    from app.utils import mcp

    params = request.get_json(silent=True) or {}
    result = mcp.call_tool_sync(name, params)
    return jsonify(result)
