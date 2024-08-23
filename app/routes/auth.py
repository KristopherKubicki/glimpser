from flask import jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash
from . import auth
from app.config import USER_NAME, USER_PASSWORD_HASH, API_KEY
from app.utils.auth import login_required, generate_timed_hash, is_hash_valid


@auth.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        if username == USER_NAME and check_password_hash(USER_PASSWORD_HASH, password):
            session["logged_in"] = True
            return redirect(url_for("main.index"))
        else:
            flash("Invalid username or password")
    return render_template("login.html")


@auth.route("/logout")
@login_required
def logout():
    session.pop("logged_in", None)
    return redirect(url_for("auth.login"))


# Add other authentication-related routes here
