from __future__ import annotations

import json
from datetime import datetime

from flask import Blueprint, render_template


def create_blueprint() -> Blueprint:
    """Create and return the timeline blueprint."""

    import app.routes as routes

    bp = Blueprint("timeline", __name__)

    @bp.route("/timeline", endpoint="timeline")
    @routes.login_required
    def timeline():
        """Render a chronological list of caption and motion events."""

        events: list[dict[str, object]] = []

        session = routes.SessionLocal()
        try:
            records = (
                session.query(routes.Summary)
                .order_by(routes.Summary.timestamp.desc())
                .limit(50)
                .all()
            )
            for rec in records:
                try:
                    data = json.loads(rec.content)
                except Exception:
                    continue
                for ts, text in data.items():
                    try:
                        ts_int = int(ts)
                    except Exception:
                        try:
                            ts_int = int(datetime.fromisoformat(ts).timestamp())
                        except Exception:
                            continue
                    events.append(
                        {"timestamp": ts_int, "type": "caption", "text": text}
                    )
        finally:
            session.close()

        templates = routes.template_manager.get_templates()
        for name, template in templates.items():
            ts_str = template.get("last_motion_time")
            if not ts_str:
                continue
            try:
                ts_dt = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
            except Exception:
                continue
            events.append(
                {"timestamp": int(ts_dt.timestamp()), "type": "motion", "text": name}
            )

        events.sort(key=lambda e: e["timestamp"], reverse=True)

        return render_template("timeline.html", events=events, page_title="Timeline")

    return bp
