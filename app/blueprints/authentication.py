from __future__ import annotations

import logging
from datetime import datetime, timedelta
from ipaddress import ip_address as ip_address_module

from flask import Blueprint, current_app, request, session
from werkzeug.security import generate_password_hash


def create_blueprint() -> Blueprint:
    """Create and return the authentication blueprint."""

    from app import routes
    from app.models import User

    bp = Blueprint("authentication", __name__)

    @bp.route("/login", methods=["GET", "POST"], endpoint="login")
    def login():
        next_url = request.args.get("next")
        ip_address = request.remote_addr
        show_recovery = False
        if ip_address:
            try:
                addr = ip_address_module(ip_address)
                show_recovery = addr.is_private or addr.is_loopback
            except ValueError:
                pass
        now = datetime.now()

        if (
            ip_address in routes.login_attempts
            and routes.login_attempts[ip_address]["locked_until"] > now
        ):
            routes.flash("Too many failed attempts. Please try again later.", "error")
            logging.warning("Locked login attempt from %s", ip_address)
            return (
                routes.render_template(
                    "login.html", page_title="Login", show_recovery_note=show_recovery
                ),
                429,
            )

        if request.method == "POST":
            username = (request.form.get("username") or "").strip()
            password = (request.form.get("password") or "").strip()
            remember = request.form.get("remember") == "on"
            if not username or not password:
                logging.debug("Login failed: missing credentials from %s", ip_address)
                routes.flash("Username and password are required", "error")
                return (
                    routes.render_template(
                        "login.html",
                        page_title="Login",
                        show_recovery_note=show_recovery,
                    ),
                    400,
                )

            db_session = routes.SessionLocal()
            try:
                user = db_session.query(User).filter_by(username=username).first()
            finally:
                db_session.close()

            if user and routes.check_password_hash(user.password_hash, password):
                session["user_id"] = user.id
                if remember:
                    current_app.permanent_session_lifetime = timedelta(
                        days=routes.config.AUTO_LOGIN_DAYS
                    )
                    session["remember"] = True
                    timeout = timedelta(days=routes.config.AUTO_LOGIN_DAYS)
                else:
                    current_app.permanent_session_lifetime = timedelta(
                        minutes=routes.config.SESSION_TIMEOUT_MINUTES
                    )
                    session.pop("remember", None)
                    timeout = timedelta(minutes=routes.config.SESSION_TIMEOUT_MINUTES)
                session["expiry"] = (now + timeout).strftime("%Y-%m-%d %H:%M:%S")
                session.permanent = True
                routes.login_attempts.pop(ip_address, None)
                logging.info("Successful login for %s from %s", username, ip_address)
                if routes.is_temp_password_required(user):
                    session["force_password_reset"] = True
                    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    routes.update_setting(
                        "LAST_PASSWORD_RESET_REQUIRED_AT", stamp, restart=False
                    )
                    routes.update_setting(
                        "LAST_PASSWORD_RESET_REQUIRED_BY",
                        user.username,
                        restart=False,
                    )
                    logging.warning(
                        "Temp password login for %s from %s; forcing reset",
                        username,
                        ip_address,
                    )
                    routes.flash(
                        "Password reset required. Please set a new password.",
                        "warning",
                    )
                    return routes.redirect(
                        routes.url_for("authentication.reset_password")
                    )
                target = (
                    next_url
                    if routes.is_safe_redirect_url(next_url)
                    else routes.url_for("index")
                )
                return routes.redirect(target)
            else:
                if ip_address not in routes.login_attempts:
                    routes.login_attempts[ip_address] = {
                        "attempts": 1,
                        "locked_until": now,
                    }
                else:
                    routes.login_attempts[ip_address]["attempts"] += 1

                if routes.login_attempts[ip_address]["attempts"] >= 5:
                    routes.login_attempts[ip_address]["locked_until"] = now + timedelta(
                        hours=24
                    )

                if routes.login_attempts[ip_address]["attempts"] % 2 == 0:
                    routes.login_attempts[ip_address]["locked_until"] = now + timedelta(
                        minutes=1
                    )

                if not user:
                    logging.warning(
                        "Login failed: unknown username '%s' from %s",
                        username,
                        ip_address,
                    )
                else:
                    logging.warning(
                        "Login failed: incorrect password for %s from %s",
                        username,
                        ip_address,
                    )
                logging.debug(
                    "Failed login attempt count %s from %s",
                    routes.login_attempts[ip_address]["attempts"],
                    ip_address,
                )
                routes.flash("Invalid username or password", "error")
        return routes.render_template(
            "login.html", page_title="Login", show_recovery_note=show_recovery
        )

    @bp.route("/sso", methods=["GET"], endpoint="sso_login")
    def sso_login():
        token = request.args.get("token") or request.headers.get("X-SSO-Token")
        if token != routes.config.SSO_TOKEN or not token:
            routes.flash("Invalid SSO token", "error")
            logging.warning("Invalid SSO token from %s", request.remote_addr)
            return routes.redirect(routes.url_for("login"))

        db_session = routes.SessionLocal()
        try:
            user = (
                db_session.query(User)
                .filter_by(username=routes.config.SSO_USERNAME)
                .first()
            )
        finally:
            db_session.close()

        if not user:
            routes.flash("Configured SSO user not found", "error")
            logging.error("SSO user %s not found", routes.config.SSO_USERNAME)
            return routes.redirect(routes.url_for("login"))

        session["user_id"] = user.id
        session["expiry"] = (
            datetime.now() + timedelta(minutes=routes.config.SESSION_TIMEOUT_MINUTES)
        ).strftime("%Y-%m-%d %H:%M:%S")
        session.permanent = True
        routes.flash("Logged in via SSO", "success")
        logging.info("SSO login for %s from %s", user.username, request.remote_addr)
        return routes.redirect(routes.url_for("index"))

    @bp.route("/logout", endpoint="logout")
    @routes.login_required
    def logout():
        session.pop("user_id", None)
        routes.flash("You have been logged out successfully.", "success")
        return routes.redirect(routes.url_for("login", logout="1"))

    @bp.route("/reset-password", methods=["GET", "POST"], endpoint="reset_password")
    @routes.login_required
    def reset_password():
        db_session = routes.SessionLocal()
        try:
            user = db_session.query(User).filter_by(id=session.get("user_id")).first()
            if not user:
                session.pop("user_id", None)
                routes.flash("Session expired. Please log in again.", "error")
                return routes.redirect(routes.url_for("login"))

            if request.method == "POST":
                password = (request.form.get("password") or "").strip()
                confirm = (request.form.get("confirm_password") or "").strip()

                if not password or not confirm:
                    routes.flash("Password and confirmation are required.", "error")
                elif len(password) < 8:
                    routes.flash("Password must be at least 8 characters.", "error")
                elif password != confirm:
                    routes.flash("Passwords do not match.", "error")
                elif routes.check_password_hash(user.password_hash, password):
                    routes.flash(
                        "New password must be different from the old password.",
                        "error",
                    )
                else:
                    user.password_hash = generate_password_hash(password)
                    user.temp_password_required = False
                    db_session.commit()
                    session.pop("force_password_reset", None)

                    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    routes.update_setting(
                        "LAST_PASSWORD_RESET_COMPLETED_AT", stamp, restart=False
                    )
                    routes.update_setting(
                        "LAST_PASSWORD_RESET_COMPLETED_BY",
                        user.username,
                        restart=False,
                    )
                    logging.info(
                        "Password reset completed for %s from %s",
                        user.username,
                        request.remote_addr,
                    )
                    routes.flash("Password updated successfully.", "success")
                    return routes.redirect(routes.url_for("index"))

            return routes.render_template(
                "reset_password.html",
                page_title="Reset Password",
                force_reset=session.get("force_password_reset", False),
            )
        finally:
            db_session.close()

    return bp
