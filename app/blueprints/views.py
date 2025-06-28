from __future__ import annotations

from flask import Blueprint


def create_blueprint() -> Blueprint:
    """Create and return the main views blueprint."""

    import app.routes as routes

    bp = Blueprint("views", __name__)

    @bp.route("/", endpoint="index")
    @routes.login_required
    def index():
        """Render the index page with available templates."""

        template_details = routes.template_manager.get_templates()
        return routes.render_template(
            "index.html",
            template_details=template_details,
            page_title="Dashboard",
        )

    @bp.route("/group/<string:group_name>", endpoint="group_page")
    @routes.login_required
    def group_page(group_name: str):
        """Render a page listing all cameras in a group."""

        group_name = routes.secure_filename(group_name)
        groups = routes.get_active_groups()
        if group_name == "all":
            return routes.redirect(routes.url_for("index"))
        if group_name not in groups:
            routes.abort(404)
        return routes.render_template(
            "group.html",
            group_name=group_name,
            page_title=f"Group – {group_name}",
        )

    return bp
