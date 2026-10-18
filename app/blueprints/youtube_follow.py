"""Private, short-lived signaling for an explicitly shared browser tab.

Video stays on a direct WebRTC connection. SQLite holds only bounded negotiation
state, shared across web workers; no capture, archive, Google login or relay.
"""

import os
import sqlite3
import time
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from flask import (
    Blueprint,
    abort,
    current_app,
    jsonify,
    redirect,
    render_template,
    request,
    session,
)

LEASE_SECONDS = 90
MAX_VIEWERS = 3


@contextmanager
def signaling_store():
    """Open a private signaling transaction and expire abandoned leases."""
    path = Path(
        current_app.config.get(
            "YOUTUBE_FOLLOW_DB",
            Path(current_app.instance_path) / "youtube-follow" / "signals.sqlite3",
        )
    )
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    connection = sqlite3.connect(path, timeout=3)
    os.chmod(path, 0o600)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA secure_delete=ON")
        connection.execute(
            "CREATE TABLE IF NOT EXISTS sources (id TEXT PRIMARY KEY, owner INTEGER UNIQUE, touched REAL)"
        )
        connection.execute(
            "CREATE TABLE IF NOT EXISTS peers (id TEXT PRIMARY KEY, source TEXT, touched REAL, offer TEXT, answer TEXT)"
        )
        connection.execute("BEGIN IMMEDIATE")
        cutoff = time.time() - LEASE_SECONDS
        connection.execute("DELETE FROM sources WHERE touched < ?", (cutoff,))
        connection.execute(
            "DELETE FROM peers WHERE touched < ? OR source NOT IN (SELECT id FROM sources)",
            (cutoff,),
        )
        yield connection
        connection.commit()
    finally:
        connection.close()


def description(kind):
    """Validate a bounded RTC session description, never an arbitrary URL."""
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or data.get("type") != kind:
        abort(400)
    sdp = data.get("sdp")
    if (
        not isinstance(sdp, str)
        or not sdp.startswith("v=0")
        or not 20 < len(sdp) <= 32768
    ):
        abort(400)
    return sdp


def source_for(db, ident):
    """Require the source to belong to the authenticated Glimpser user."""
    row = db.execute(
        "SELECT * FROM sources WHERE id=? AND owner=?", (ident, session["user_id"])
    ).fetchone()
    if row is None:
        abort(404)
    return row


def create_blueprint():
    """Build the opt-in YouTube follow page and its private signaling routes."""
    bp = Blueprint("youtube_follow", __name__, url_prefix="/youtube-follow")

    @bp.before_request
    def authorize():
        # Personal playback is stricter than LAN camera browsing: no guest,
        # API-key-in-URL, or public-profile fallback grants access to this page.
        owner = session.get("user_id")
        valid = (
            type(owner) is int and owner > 0 and not session.get("force_password_reset")
        )
        expiry = session.get("expiry")
        try:
            if expiry and datetime.now() > datetime.strptime(
                expiry, "%Y-%m-%d %H:%M:%S"
            ):
                valid = False
        except (ValueError, TypeError):
            valid = False
        if not valid:
            if request.endpoint == "youtube_follow.page":
                return redirect("/login?next=/youtube-follow")
            return jsonify(error="Sign in to Glimpser to view personal playback."), 401
        if request.method not in {"GET", "HEAD"}:
            # TLS may terminate at the existing reverse proxy. Match the Host
            # exactly; never trust an arbitrary forwarded host or allow a CORS origin.
            allowed_origins = {request.host_url.rstrip("/"), "https://" + request.host}
            if request.headers.get("Origin") not in allowed_origins:
                abort(403)
            if request.content_length is None:
                abort(411)
            if request.content_length > 40000:
                abort(413)
            if not request.is_json:
                abort(415)

    @bp.after_request
    def private_response(response):
        response.headers["Cache-Control"] = "no-store, private"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        return response

    @bp.get("")
    def page():
        return render_template("youtube_follow.html")

    @bp.get("/state")
    def state():
        with signaling_store() as db:
            row = db.execute(
                "SELECT id FROM sources WHERE owner=?", (session["user_id"],)
            ).fetchone()
        return jsonify(source=row["id"] if row else None)

    @bp.post("/publish")
    def publish():
        with signaling_store() as db:
            if db.execute(
                "SELECT id FROM sources WHERE owner=?", (session["user_id"],)
            ).fetchone():
                return jsonify(
                    error="A tab is already shared. Stop it there before sharing another."
                ), 409
            ident = uuid.uuid4().hex
            db.execute(
                "INSERT INTO sources VALUES (?, ?, ?)",
                (ident, session["user_id"], time.time()),
            )
        return jsonify(id=ident), 201

    @bp.route("/publish/<ident>", methods=["POST", "DELETE"])
    def publisher(ident):
        with signaling_store() as db:
            source_for(db, ident)
            if request.method == "DELETE":
                db.execute("DELETE FROM peers WHERE source=?", (ident,))
                db.execute("DELETE FROM sources WHERE id=?", (ident,))
                return jsonify(stopped=True)
            db.execute("UPDATE sources SET touched=? WHERE id=?", (time.time(), ident))
            peers = db.execute(
                "SELECT id, offer, answer FROM peers WHERE source=?", (ident,)
            ).fetchall()
            return jsonify(
                peers=[
                    {
                        "id": p["id"],
                        "offer": p["offer"] if p["answer"] is None else None,
                    }
                    for p in peers
                ]
            )

    @bp.post("/publish/<ident>/answer/<peer>")
    def answer(ident, peer):
        sdp = description("answer")
        with signaling_store() as db:
            source_for(db, ident)
            result = db.execute(
                "UPDATE peers SET answer=? WHERE id=? AND source=? AND answer IS NULL",
                (sdp, peer, ident),
            )
            if result.rowcount != 1:
                abort(409)
        return jsonify(ok=True)

    @bp.post("/connect/<ident>")
    def connect(ident):
        sdp = description("offer")
        with signaling_store() as db:
            source_for(db, ident)
            if (
                db.execute(
                    "SELECT COUNT(*) FROM peers WHERE source=?", (ident,)
                ).fetchone()[0]
                >= MAX_VIEWERS
            ):
                return jsonify(error="Three displays are already connected."), 429
            peer = uuid.uuid4().hex
            db.execute(
                "INSERT INTO peers VALUES (?, ?, ?, ?, NULL)",
                (peer, ident, time.time(), sdp),
            )
        return jsonify(id=peer), 201

    @bp.route("/peer/<peer>", methods=["POST", "DELETE"])
    def viewer(peer):
        with signaling_store() as db:
            row = db.execute(
                "SELECT peers.* FROM peers JOIN sources ON sources.id=peers.source WHERE peers.id=? AND sources.owner=?",
                (peer, session["user_id"]),
            ).fetchone()
            if row is None:
                abort(404)
            if request.method == "DELETE":
                db.execute("DELETE FROM peers WHERE id=?", (peer,))
                return jsonify(stopped=True)
            db.execute("UPDATE peers SET touched=? WHERE id=?", (time.time(), peer))
            return jsonify(answer=row["answer"])

    return bp
