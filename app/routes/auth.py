from flask import Blueprint, request, render_template, flash, redirect, url_for, session
from datetime import datetime, timedelta
from . import config, SessionLocal, User
from . import login_required
import logging

bp = Blueprint("auth", __name__)


@bp.route("/login", methods=["GET", "POST"], endpoint="login")
def login():
    from . import login_attempts, SessionLocal, check_password_hash

    ip_address = request.remote_addr
    now = datetime.now()
    if (
        ip_address in login_attempts
        and login_attempts[ip_address]["locked_until"] > now
    ):
        flash("Too many failed attempts. Please try again later.", "error")
        logging.warning("Locked login attempt from %s", ip_address)
        return render_template("login.html", page_title="Login"), 429

    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = (request.form.get("password") or "").strip()
        if not username or not password:
            flash("Username and password are required", "error")
            return render_template("login.html", page_title="Login"), 400

        db_session = SessionLocal()
        try:
            user = db_session.query(User).filter_by(username=username).first()
        finally:
            db_session.close()

        if user and check_password_hash(user.password_hash, password):
            session["user_id"] = user.id
            session["expiry"] = (
                now + timedelta(minutes=config.SESSION_TIMEOUT_MINUTES)
            ).strftime("%Y-%m-%d %H:%M:%S")
            session.permanent = True
            login_attempts.pop(ip_address, None)
            logging.info("Successful login for %s from %s", username, ip_address)
            return redirect(url_for("index"))
        else:
            if ip_address not in login_attempts:
                login_attempts[ip_address] = {"attempts": 1, "locked_until": now}
            else:
                login_attempts[ip_address]["attempts"] += 1
            if login_attempts[ip_address]["attempts"] >= 5:
                login_attempts[ip_address]["locked_until"] = now + timedelta(hours=24)
            if login_attempts[ip_address]["attempts"] % 2 == 0:
                login_attempts[ip_address]["locked_until"] = now + timedelta(minutes=1)
            logging.warning("Failed login attempt for %s from %s", username, ip_address)
            flash("Invalid username or password", "error")
    return render_template("login.html", page_title="Login")


@bp.route("/sso", methods=["GET"], endpoint="sso_login")
def sso_login():
    from . import SessionLocal

    token = request.args.get("token") or request.headers.get("X-SSO-Token")
    if token != config.SSO_TOKEN or not token:
        flash("Invalid SSO token", "error")
        logging.warning("Invalid SSO token from %s", request.remote_addr)
        return redirect(url_for("auth.login"))

    db_session = SessionLocal()
    try:
        user = db_session.query(User).filter_by(username=config.SSO_USERNAME).first()
    finally:
        db_session.close()

    if not user:
        flash("Configured SSO user not found", "error")
        logging.error("SSO user %s not found", config.SSO_USERNAME)
        return redirect(url_for("auth.login"))

    session["user_id"] = user.id
    session["expiry"] = (
        datetime.now() + timedelta(minutes=config.SESSION_TIMEOUT_MINUTES)
    ).strftime("%Y-%m-%d %H:%M:%S")
    session.permanent = True
    flash("Logged in via SSO", "success")
    logging.info("SSO login for %s from %s", user.username, request.remote_addr)
    return redirect(url_for("index"))


@bp.route("/logout", endpoint="logout")
@login_required
def logout():
    session.pop("user_id", None)
    flash("You have been logged out successfully.", "success")
    return redirect(url_for("auth.login"))
