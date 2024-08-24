from app.models import Summary
from app.utils.db import SessionLocal

    @app.route("/captions")
    @login_required
    def captions():
        session = SessionLocal()
        try:
            # Fetch the last 5 summaries from the database
            entries = session.query(Summary).order_by(Summary.timestamp.desc()).limit(5).all()
            
            # Convert the Summary objects to dictionaries
            entries = [
                {entry.timestamp: json.loads(entry.content)}
                for entry in entries
            ]
        finally:
            session.close()

        # Get a list of active cameras (with updates within the last 1 day)
        return render_template(
            "captions.html",
            template_details=template_manager.get_templates(),
            lcaptions=entries,
        )

    @app.route("/live")
    @login_required
    def live():
        # Get a list of active cameras (with updates within the last 1 day)
        return render_template(
            "live.html", template_details=template_manager.get_templates()
        )