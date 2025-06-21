from flask import Blueprint, jsonify

from app.utils.network import is_system_online


def create_blueprint() -> Blueprint:
    """Create and return the network status blueprint."""

    from app.routes import login_required

    bp = Blueprint("network", __name__)

    @bp.route("/network_status")
    @login_required
    def network_status():
        """Return current network connectivity status."""

        return jsonify({"online": is_system_online()})

    return bp
