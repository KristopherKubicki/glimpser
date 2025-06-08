# Architecture Overview

This guide provides a high-level look at Glimpser's core components and how they interact.

## Flask Application Initialization (`app/__init__.py`)

- Creates the Flask application instance.
- Loads configuration values and sets up logging.
- Initializes routes from `app/routes.py`.
- Starts the background scheduler and optional watchdog thread.
  The watchdog performs health checks every 30 seconds and only triggers
  a restart after a configurable number of failures. Tune
  `WATCHDOG_FAILURE_THRESHOLD`, `WATCHDOG_RESTART_COOLDOWN`,
  `WATCHDOG_MAX_FILE_HANDLES`, `WATCHDOG_CPU_THRESHOLD` and
  `WATCHDOG_MEMORY_THRESHOLD` to adjust this behaviour. When repeated
  failures occur the watchdog calls `sys.exit(1)`, so run Glimpser under a
  supervisor that automatically restarts the process. Requests to `/health`
  include the configured API
  key so the check succeeds even when login is required. See the
  `glimpser.service` snippet in `build_packages.sh` or the `restart`
  option in `docker-compose.yaml` for examples of how to enable
  automatic restarts.

## Configuration Handling (`app/config.py`)

- Loads environment variables and values stored in the database.
- Exposes settings such as `SECRET_KEY`, database location and retention policy limits.
- Includes helper functions to back up and restore configuration state.

## Utility Modules (`app/utils/`)

- Collection of helpers for image processing, database access, notifications and more.
- Key modules include:
  - `db.py` – SQLAlchemy setup and database initialization.
  - `screenshots.py` – capturing or downloading images and videos.
  - `template_manager.py` – provides `TemplateManager` for validating,
    saving and deleting templates stored in the database.
  - `email_alerts.py`, `sms_alerts.py` and `cap_alerts.py` – sending notifications.

## Scheduler Jobs (`app/utils/scheduling.py`)

- Uses APScheduler to run periodic tasks.
- Jobs include crawler scheduling, video archiving, discovery and summarization.
- Tasks run asynchronously so functions like `schedule_discovery` and `schedule_summarization` never block the caller.
- Background components start in a low-priority thread so Flask can serve requests immediately.
- Exposes a `GracefulAPScheduler` instance used by the Flask app.
- Stale crawler jobs are removed when templates are updated.

## How Components Fit Together

```
 Client Request ---> Routes (app/routes.py) ----> Models (app/models/) ----> Database
                           |                           |
                           v                           v
                     Utility Functions ----> Scheduler Jobs / Background Tasks
```

- Routes handle incoming API or web requests.
- Models define the database schema.
- Utility functions perform processing and are called by both routes and scheduled jobs.
- Background tasks run outside request/response cycles to capture data and generate summaries.

## Data Flow from Camera to UI

1. **Camera Source** – Each camera is defined in the database as a template specifying the capture URL and parameters.
2. **Capture Job** – The scheduler runs `capture_template` jobs that use `screenshots.py` to grab frames or video from the source.
3. **Database Update** – Captured metadata and any motion events are stored via `db.py` while images are written to `data/screenshots/`.
4. **Summarization** – `update_summary` collects recent captions and calls the configured language model to produce a textual summary which is saved back to the database.
5. **Routes and API** – Flask routes load screenshots and summaries to serve HTML pages or JSON responses.
6. **Frontend Display** – The web interface streams MJPEG or MP4 data on the live page and displays captions or summaries as they arrive via WebSocket events.
