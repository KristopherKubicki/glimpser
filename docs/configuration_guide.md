# Glimpser Configuration Guide

This guide describes the configuration options available in Glimpser. Most
settings can be modified from the web interface. A few can be overridden with
environment variables before starting the application.

## Environment Variables

The following environment variables are read in `app/config.py` and allow you to
change where runtime data is stored. If not provided, the defaults shown below
are used.

| Variable | Default | Purpose |
| --- | --- | --- |
| `GLIMPSER_DATABASE_PATH` | `data/glimpser.db` | Location of the SQLite database file |
| `GLIMPSER_LOGGING_PATH` | `logs/glimpser.log` | Path to the main log file |
| `GLIMPSER_BACKUP_PATH` | `data/config_backup.json` | File used when backing up configuration |

## Core Settings

Below are key settings loaded from the database with their default values. You
can modify them in the application interface or directly in the database.

- `NAME` – application name (default `glimpser`)
- `VERSION` – application version (defaults to the installed package version and
  is updated automatically when it changes)
- `LANG` – default language (default `en-US`)
- `TZ` – timezone used for logs (default `UTC`)
- `HOST` – address to bind the server (default `0.0.0.0`)
- `PORT` – port for the web interface (default `8082`)
- `DEBUG` – enable debug mode (default `True`)
- `DEBUG_MODE` – runtime alias of `DEBUG` used by the command-line interface
- `MAX_WORKERS` – number of worker threads (default `8`)
- `LOG_LEVEL` – logging level (`INFO`, `WARN`, `DEBUG`, etc.)

## User Credentials

Glimpser stores login details in the settings database. These values can be
updated with `generate_credentials.py` or through the web interface.

- `USER_NAME` – default login name (default `admin`)
- `USER_PASSWORD_HASH` – hashed password string (empty by default)
- `SECRET_KEY` – secret key used for session management (default
  `default_secret_key`)
- `API_KEY` – key used to access the API (empty by default)
- `SSO_TOKEN` – token used for the `/sso` login endpoint (empty by default)
- `SSO_USERNAME` – username associated with SSO logins (defaults to `USER_NAME`)
- `CHATGPT_KEY` – API key for AI captioning and summarization (empty by
  default)
- `SESSION_COOKIE_SECURE` – set `True` to send cookies only over HTTPS
  (default `True`)
- `SESSION_COOKIE_HTTPONLY` – set `True` to prevent JavaScript access to the
  session cookie (default `True`)
- `SESSION_TIMEOUT_MINUTES` – session lifetime in minutes (default `30`)

User accounts are stored in the `users` table. Each record contains the
`username`, `password_hash`, and an optional `role` that can be used for future
permission checks. The `generate_credentials.py` utility keeps the settings and
user table in sync.

## File Locations

- `SCREENSHOT_DIRECTORY` – directory for raw screenshots (default `data/screenshots/`)
- `VIDEO_DIRECTORY` – directory for recorded videos (default `data/video/`)

You can change these paths via the settings table or by editing `app/config.py` if you maintain a custom build.

## Email Settings

To enable email notifications, configure the following:

- `EMAIL_ENABLED` – set to `True` to enable sending emails (default `False`)
- `EMAIL_SENDER` – the "from" address (default `your-email@example.com`)
- `EMAIL_RECIPIENTS` – comma-separated list of recipients (default `recipient1@example.com,recipient2@example.com`)
- `EMAIL_SMTP_SERVER` – SMTP server address (default `smtp.example.com`)
- `EMAIL_SMTP_PORT` – server port (default `587`)
- `EMAIL_USE_TLS` – whether to use TLS (default `True`)
- `EMAIL_USERNAME` and `EMAIL_PASSWORD` – authentication credentials (default user name `your-username`)

## SMS Settings

Configure these values to enable Twilio SMS alerts:

- `TWILIO_SID` – your Twilio account SID
- `TWILIO_TOKEN` – your Twilio auth token
- `TWILIO_NUMBER` – phone number that receives alerts

## CAP Settings

Set these variables to enable Common Alerting Protocol alerts:

- `CAP_ENDPOINT` – URL that accepts CAP XML alerts
- `CAP_SENDER` – identifier used in the CAP `sender` field

## Capture Parameters

Settings controlling how frames are captured from video sources:

- `NUM_FRAMES` – number of frames to grab from each stream (default `3`)
- `CAPTURE_TIMEOUT` – maximum seconds to wait for a frame; also used as the timeout for download and ffmpeg operations (default `30`)
- `PROBE_SIZE_DEFAULT` – probe size for HTTP/HTTPS streams (default `5M`)
- `PROBE_SIZE_RTSP` – probe size for RTSP streams (default `10M`)
- `PROBE_SIZE_OTHER` – probe size for other protocols (default `20M`)

## Advanced Options

Additional variables control AI behaviour and external tools:

- `LLM_MODEL_VERSION` – language model version to use (default `gpt-4.1-mini`)
- `LLM_SUMMARY_PROMPT` – default prompt used for log summaries
- `LLM_CAPTION_PROMPT` – default prompt used for image captions
- `FFMPEG_PATH` – path to the `ffmpeg` binary (default `ffmpeg`)
- `FFPROBE_PATH` – path to the `ffprobe` binary (default `ffprobe`)
- `FFMPEG_HWACCEL` – hardware acceleration mode for ffmpeg (`False` disables)

Refer to the code comments in `app/config.py` for full details on each setting.
