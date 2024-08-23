from flask import render_template
from . import main
from app.utils.auth import login_required
from app.utils import template_manager


@main.route("/")
@login_required
def index():
    return render_template("index.html")


@main.route("/stream")
@login_required
def stream():
    return render_template("stream.html")


@main.route("/live")
@login_required
def live():
    return render_template(
        "live.html", template_details=template_manager.get_templates()
    )


@main.route("/captions")
@login_required
def captions():
    # Implement the logic for captions route
    pass


# Add other main application routes here
