# Glimpser Configuration Guide

This guide describes the configuration options available in Glimpser. Most settings can be modified from the web interface. Some can also be controlled with environment variables before starting the application.

## Environment Variables

The following variables can be set to override default paths:

| Variable | Description | Default |
| --- | --- | --- |
| `GLIMPSER_DATABASE_PATH` | Location of the SQLite database file | `data/glimpser.db` |
| `GLIMPSER_LOGGING_PATH` | Path to the main log file | `logs/glimpser.log` |
| `GLIMPSER_BACKUP_PATH` | Path for configuration backups | `data/config_backup.json` |

These variables are read in `app/config.py` and allow you to place data or logs in custom locations.

## Core Settings

Below are key settings loaded from the database with their default values. You can modify them in the application interface or directly in the database.

- `HOST` – address to bind the server (default `0.0.0.0`)
- `PORT` – port for the web interface (default `8082`)
- `DEBUG` – enable debug mode (`True` or `False`)
- `SECRET_KEY` – secret key for session management
- `API_KEY` – key used to access the API
- `CHATGPT_KEY` – API key for AI captioning and summarization
- `MAX_WORKERS` – number of worker threads
- `LOG_LEVEL` – logging level (`INFO`, `WARN`, `DEBUG`, etc.)

## File Locations

- `SCREENSHOT_DIRECTORY` – directory for raw screenshots
- `VIDEO_DIRECTORY` – directory for recorded videos
- `SUMMARIES_DIRECTORY` – directory where summaries are written

You can change these paths via the settings table or by editing `app/config.py` if you maintain a custom build.

## Email Settings

To enable email notifications, configure the following:

- `EMAIL_ENABLED` – set to `True` to enable sending emails
- `EMAIL_SENDER` – the "from" address
- `EMAIL_RECIPIENTS` – comma-separated list of recipients
- `EMAIL_SMTP_SERVER` – SMTP server address
- `EMAIL_SMTP_PORT` – server port
- `EMAIL_USE_TLS` – whether to use TLS (`True`/`False`)
- `EMAIL_USERNAME` and `EMAIL_PASSWORD` – authentication credentials

## Advanced Options

Additional variables in `app/config.py` control video capture and AI behavior:

- `NUM_FRAMES`, `CAPTURE_TIMEOUT`, and probe size settings for video capture
- `LLM_MODEL_VERSION`, `LLM_SUMMARY_PROMPT`, and `LLM_CAPTION_PROMPT` for summarization and captioning
- `FFMPEG_PATH` and `FFPROBE_PATH` for specifying custom binaries

Refer to the code comments in `app/config.py` for full details on each setting.
