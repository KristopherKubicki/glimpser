from flask import Blueprint, current_app, jsonify, make_response, render_template

from app.utils.network import is_system_online, network_state


def create_blueprint() -> Blueprint:
    """Create and return the network status blueprint."""

    from app import routes

    bp = Blueprint("network", __name__)

    @bp.route("/network_status")
    def network_status():
        """Return current connectivity state for UI banners and live recovery."""

        # Distinguish between "the box lost all connectivity" and
        # "WAN/DNS is flaky but local cameras are still reachable". Treat the
        # latter as degraded instead of fully offline so /live pages do not
        # falsely advertise offline mode while LAN-backed views still work.
        #
        # Keep this endpoint unauthenticated. Live pages poll it in the
        # background to decide whether to show "offline mode". If the route
        # redirects to /login after a stale session, the browser interprets the
        # HTML redirect as a network failure and incorrectly flips the player to
        # offline even though the server is still up.
        state = network_state()
        internet_ok = is_system_online()
        lan_ok = bool(state.get("lan_ok", False))
        online = bool(lan_ok or internet_ok)
        degraded = bool(online and not internet_ok)

        return jsonify(
            {
                "online": online,
                "degraded": degraded,
                "internet": internet_ok,
                "lan": lan_ok,
                "dns": bool(state.get("dns_ok", False)),
                "wan": bool(state.get("wan_ok", False)),
                "asset_version": str(current_app.config.get("ASSET_VERSION", "")),
            }
        )

    @bp.route("/house-systems")
    @routes.login_required
    def house_systems():
        """Show logical service placement and explicitly scoped reachability."""
        from app.utils.house_system_map import GROUPS, snapshot

        response = make_response(
            render_template("house_systems.html", system_map=snapshot(), groups=GROUPS)
        )
        response.headers["Cache-Control"] = "no-store"
        return response

    return bp
