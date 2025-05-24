# Architecture Overview

This guide provides a high-level look at Glimpser's core components and how they interact.

## Flask Application Initialization (`app/__init__.py`)
- Creates the Flask application instance.
- Loads configuration values and sets up logging.
- Initializes routes from `app/routes.py`.
- Starts the background scheduler and optional watchdog thread.

## Configuration Handling (`app/config.py`)
- Loads environment variables and values stored in the database.
- Exposes settings such as `SECRET_KEY`, database location and retention policy limits.
- Includes helper functions to back up and restore configuration state.

## Utility Modules (`app/utils/`)
- Collection of helpers for image processing, database access, notifications and more.
- Key modules include:
  - `db.py` – SQLAlchemy setup and database initialization.
  - `screenshots.py` – capturing or downloading images and videos.
  - `template_manager.py` – management of capture templates.
  - `email_alerts.py` and `sms_alerts.py` – sending notifications.

## Scheduler Jobs (`app/utils/scheduling.py`)
- Uses APScheduler to run periodic tasks.
- Jobs include crawler scheduling, video archiving and summarization.
- Exposes a `GracefulAPScheduler` instance used by the Flask app.

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

