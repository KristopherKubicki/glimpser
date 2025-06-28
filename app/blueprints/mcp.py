from __future__ import annotations

from flask import Blueprint, jsonify, request


def create_blueprint() -> Blueprint:
    """Create and return the MCP integration blueprint."""

    from app import routes

    bp = Blueprint("mcp", __name__)

    @bp.route("/mcp/tools")
    @routes.login_required
    def mcp_tools():
        """Return the list of tools exposed by the configured MCP server."""

        from app.utils import mcp

        tools = mcp.list_tools_sync()
        return jsonify(tools)

    @bp.route("/mcp/tool/<string:name>", methods=["POST"])
    @routes.login_required
    def mcp_call_tool(name: str):
        """Call a tool on the configured MCP server."""

        from app.utils import mcp

        params = request.get_json(silent=True) or {}
        result = mcp.call_tool_sync(name, params)
        return jsonify(result)

    return bp
