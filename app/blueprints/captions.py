from __future__ import annotations

from flask import Blueprint, Response, jsonify, redirect, url_for, flash


def create_blueprint() -> Blueprint:
    """Create and return the captions management blueprint."""

    import app.routes as routes

    bp = Blueprint("captions", __name__)

    @bp.route("/captions")
    @routes.login_required
    def captions():
        cost_start = routes.request.args.get("cost_start")
        cost_end = routes.request.args.get("cost_end")

        entries = []
        latest_caption = ""
        try:
            session_db = routes.SessionLocal()
            try:
                records = (
                    session_db.query(routes.Summary)
                    .order_by(routes.Summary.timestamp.desc())
                    .limit(100)
                    .all()
                )
                for rec in records:
                    try:
                        data = routes.json.loads(rec.content)
                        for ts, text in data.items():
                            try:
                                dt = routes.datetime.utcfromtimestamp(int(ts))
                                iso_ts = dt.strftime("%Y-%m-%dT%H:%M:%SZ")
                            except Exception:
                                iso_ts = ts
                            entries.append({iso_ts: text})
                    except Exception as exc:
                        routes.logging.error("Failed to parse captions: %s", exc)
            finally:
                session_db.close()
        except Exception:
            entries = []

        if entries:
            try:
                latest_caption = next(iter(entries[0].values()))
            except Exception:
                latest_caption = ""

        templates = routes.template_manager.get_templates()
        for name, template in templates.items():
            last_screenshot_time = template.get("last_screenshot_time")
            frequency = int(template.get("frequency", 30))

            if last_screenshot_time:
                last_screenshot = routes.datetime.strptime(
                    last_screenshot_time, "%Y-%m-%d %H:%M:%S"
                )
                next_screenshot = last_screenshot + routes.timedelta(minutes=frequency)
                template["next_screenshot_time"] = next_screenshot.strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
            else:
                template["next_screenshot_time"] = None

            templates[name]["screenshot_count"] = (
                routes.template_manager.get_screenshot_count(name)
            )
            templates[name]["video_count"] = routes.template_manager.get_video_count(
                name
            )
            templates[name]["storage_usage"] = (
                routes.template_manager.get_storage_usage(name)
            )
            templates[name]["storage_usage_bytes"] = (
                routes.template_manager.get_storage_usage_bytes(name)
            )
            templates[name]["llm_response_count"] = (
                routes.template_manager.get_llm_response_count(name)
            )
            templates[name]["llm_cost_estimate"] = (
                routes.template_manager.get_llm_cost_estimate(
                    name, start_date=cost_start, end_date=cost_end
                )
            )

        return routes.render_template(
            "captions.html",
            template_details=templates,
            lcaptions=entries,
            latest_caption=latest_caption,
            page_title="Captions",
            cost_start=cost_start,
            cost_end=cost_end,
        )

    @bp.route("/download_captions_tsv")
    @routes.login_required
    def download_captions_tsv():
        templates = routes.template_manager.get_templates()

        output = routes.io.StringIO()
        writer = routes.csv.writer(output, delimiter="\t")

        writer.writerow(["name", "groups", "notes", "last_caption"])

        for name, template in templates.items():
            writer.writerow(
                [
                    name,
                    template.get("groups", ""),
                    template.get("notes", ""),
                    template.get("last_caption", ""),
                ]
            )

        output.seek(0)
        return Response(
            output.getvalue(),
            mimetype="text/tab-separated-values",
            headers={"Content-Disposition": "attachment;filename=captions.tsv"},
        )

    @bp.route("/upload_captions_tsv", methods=["POST"])
    @routes.login_required
    def upload_captions_tsv():
        if "tsv_file" not in routes.request.files:
            flash("No file part", "error")
            return redirect(routes.url_for("captions"))

        file = routes.request.files["tsv_file"]

        if file.filename == "":
            flash("No selected file", "error")
            return redirect(routes.url_for("captions"))

        if file and file.filename.endswith(".tsv"):
            stream = routes.io.StringIO(file.stream.read().decode("UTF8"), newline=None)
            reader = routes.csv.reader(stream, delimiter="\t")

            next(reader, None)

            updated_count = 0
            for row in reader:
                if len(row) >= 4:
                    name, groups, notes, last_caption = row[:4]

                    template_name = routes.validate_template_name(name)
                    if template_name is None:
                        continue

                    template = routes.template_manager.get_template(template_name)
                    if template:
                        updates = {"groups": groups, "notes": notes}

                        if last_caption and last_caption != template.get(
                            "last_caption", ""
                        ):
                            updates["last_caption"] = last_caption
                            updates["last_caption_time"] = (
                                routes.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
                            )

                        if routes.template_manager.save_template(
                            template_name, updates
                        ):
                            updated_count += 1

            flash(f"Successfully updated {updated_count} templates", "success")
            return redirect(routes.url_for("captions"))

        flash("Invalid file format. Please upload a TSV file.", "error")
        return redirect(routes.url_for("captions"))

    @bp.route("/captions_chat", methods=["POST"])
    @routes.login_required
    def captions_chat():
        data = routes.request.get_json(force=True) or {}
        question = (data.get("question") or "").strip()
        if not question:
            return jsonify({"error": "Missing question"}), 400

        start = data.get("start")
        end = data.get("end")

        session_db = routes.SessionLocal()
        try:
            query = session_db.query(routes.Summary).order_by(
                routes.Summary.timestamp.desc()
            )
            if start:
                try:
                    start_ts = int(routes.datetime.fromisoformat(start).timestamp())
                    query = query.filter(routes.Summary.timestamp >= start_ts)
                except (ValueError, TypeError) as exc:
                    routes.logging.warning("Invalid start parameter %s: %s", start, exc)
            if end:
                try:
                    end_ts = int(routes.datetime.fromisoformat(end).timestamp())
                    query = query.filter(routes.Summary.timestamp <= end_ts)
                except (ValueError, TypeError) as exc:
                    routes.logging.warning("Invalid end parameter %s: %s", end, exc)
            records = query.limit(101).all()
            truncated = len(records) > 100
            records = records[:100]
            captions = []
            for rec in reversed(records):
                try:
                    jdata = routes.json.loads(rec.content)
                    captions.extend(jdata.values())
                except Exception:
                    captions.append(rec.content)
        finally:
            session_db.close()

        history = "\n".join(captions)
        answer = routes.ask_question(question, history) or ""

        ts = int(routes.datetime.utcnow().timestamp())
        session_db = routes.SessionLocal()
        try:
            session_db.add(
                routes.Summary(
                    timestamp=ts, content=routes.json.dumps({ts: f"Q: {question}"})
                )
            )
            if answer:
                ts2 = ts + 1
                session_db.add(
                    routes.Summary(
                        timestamp=ts2,
                        content=routes.json.dumps({ts2: f"A: {answer}"}),
                    )
                )
            session_db.commit()
        finally:
            session_db.close()

        return jsonify({"answer": answer, "truncated": truncated})

    return bp
