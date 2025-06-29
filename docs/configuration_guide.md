# Glimpser Configuration Guide

This guide describes the configuration options available in Glimpser. Most
settings can be modified from the web interface. A few can be overridden with
environment variables before starting the application.

## Environment Variables

The following environment variables are read in `app/config.py` and allow you to
change where runtime data is stored. If not provided, the defaults shown below
are used.

| Variable                 | Default                   | Purpose                                 |
| ------------------------ | ------------------------- | --------------------------------------- |
| `GLIMPSER_DATABASE_PATH` | `data/glimpser.db`        | Location of the SQLite database file    |
| `GLIMPSER_LOGGING_PATH`  | `logs/glimpser.log`       | Path to the main log file               |
| `GLIMPSER_BACKUP_PATH`   | `data/config_backup.json` | File used when backing up configuration |
| `GLIMPSER_BACKUP_SERVER_URL` | _(empty)_ | Optional endpoint to receive uploaded backups |

Relative paths are resolved from the application's root directory. Use an
absolute path if the backup file should reside elsewhere.

`app.config` parses the `.env` file only once when it is first imported. Later
imports reuse the existing values instead of re-reading the file.

## Core Settings

Below are key settings loaded from the database with their default values. You
can modify them in the application interface or directly in the database.

- `NAME` – application name (default `glimpser`)
- `NAV_ICON` – navigation logo path relative to the `static` directory. Set to an empty string to hide the logo (default `img/glimpser_small.png`). The settings page shows the current logo and lets you upload your own PNG.
- `VERSION` – application version (defaults to the installed package version and
  is updated automatically when it changes)
- `LANG` – default language (default `en-US`). The settings page lists common language codes such as `en-US`, `es-ES`, `fr-FR`, `de-DE`, `zh-CN`, `ja-JP`, `pt-BR`, `hi-IN`, `ar-SA`, and `ru-RU`.
- `TZ` – timezone used for logs (default `UTC`). Values must exist in the system time zone database.
- `HOST` – address to bind the server (default `0.0.0.0`). The settings page lists common local addresses first.
- `ENFORCE_DOMAIN_IN_HOST` – require a domain in the `Host` header (default `False`)
- `PORT` – port for the web interface (default `8082`). Must be a free, non‑privileged port.
- `DEBUG` – enable debug mode (default `False`)
- `DEBUG_MODE` – runtime alias of `DEBUG` used by the command-line interface
- `MAX_WORKERS` – number of worker threads (default `8`). Limited to twice the CPU count.
- `LOG_LEVEL` – logging level (`INFO`, `WARN`, `DEBUG`, etc.)
- `FLASK_LOG_LEVEL` – logging level used by the Flask app logger (defaults to `LOG_LEVEL`)

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
- `SESSION_TIMEOUT_MINUTES` – session timeout after this many minutes of
  inactivity (default `30`)
- `AUTO_LOGIN_DAYS` – days the session persists when "Remember me" is checked
  (default `30`)
- `SKIP_LOGIN_SUBNETS` – comma-separated list of IPv4 or IPv6 subnets allowed
  to browse non-admin pages without logging in (empty by default)

User accounts are stored in the `users` table. Each record contains the
`username`, `password_hash`, and an optional `role` that can be used for future
permission checks. The `generate_credentials.py` utility keeps the settings and
user table in sync.

## File Locations

- `SCREENSHOT_DIRECTORY` – directory for raw screenshots (default `data/screenshots/`)
- `VIDEO_DIRECTORY` – directory for recorded videos (default `data/video/`)
- `CLIPS_DIRECTORY` – directory used to cache short clips (default `data/clips/`)
- `CLIP_REFRESH_MAX_CAMERAS` – skip clip pre-rendering when more than this many
  cameras exist (default `10`, use `0` to disable the check)
- `SUMMARIES_DIRECTORY` – **deprecated**; summaries are now stored in the database.

  Older deployments may still reference this path but it is no longer used.

You can change these paths via the settings table or by editing `app/config.py` if you maintain a custom build.

## Notification Settings

Email, SMS, and CAP alerts now appear under the **Notifications** tab.

### Email

To enable email notifications, configure the following:

- `EMAIL_ENABLED` – set to `True` to enable sending emails (default `False`)
- `EMAIL_SENDER` – the "from" address (empty by default; the field shows `your-email@example.com` as a hint)
- `EMAIL_RECIPIENTS` – comma-separated list of recipients (empty by default)
- `EMAIL_SMTP_SERVER` – SMTP server address (empty by default)
- `EMAIL_SMTP_PORT` – server port (default `587`)
- `EMAIL_SMTP_TIMEOUT` – connection timeout in seconds (default `5`)
- `EMAIL_USE_TLS` – whether to use TLS (default `True`)
- `EMAIL_USERNAME` and `EMAIL_PASSWORD` – authentication credentials (default user name `your-username`)

### SMS

Configure these values to enable Twilio SMS alerts:

- `SMS_ENABLED` – set to `True` to send SMS notifications

- `TWILIO_SID` – your Twilio account SID
- `TWILIO_TOKEN` – your Twilio auth token
- `TWILIO_FROM_NUMBER` – number that sends the messages
- `TWILIO_NUMBER` – phone number that receives alerts
- `TWILIO_FROM_NUMBER` – number used as the sender (default is `TWILIO_NUMBER`)

### Web Push

Enable push notifications with these values:

- `VAPID_PUBLIC_KEY` – Base64 encoded public key used by the browser
- `VAPID_PRIVATE_KEY` – matching private key for signing messages

### CAP

Set these variables to enable Common Alerting Protocol alerts:

- `CAP_ENABLED` – set to `True` to send CAP notifications

- `CAP_ENDPOINT` – URL that accepts CAP XML alerts (empty by default)
- `CAP_SENDER` – identifier used in the CAP `sender` field (empty by default)

## Capture Parameters

Settings controlling how frames are captured from video sources:

- `NUM_FRAMES` – number of frames to grab from each stream (default `3`)
- `CAPTURE_TIMEOUT` – maximum seconds to wait for a frame; also used as the timeout for download and ffmpeg operations (default `30`)
- `PROBE_SIZE_DEFAULT` – probe size for HTTP/HTTPS streams (default `5M`)
- `PROBE_SIZE_RTSP` – probe size for RTSP streams (default `10M`)
- `PROBE_SIZE_OTHER` – probe size for other protocols (default `20M`)
- `ANALYZE_DURATION_DEFAULT` – ffmpeg analyzeduration for HTTP/HTTPS streams (default `5M`)
- `ANALYZE_DURATION_RTSP` – analyzeduration for RTSP streams (default `10M`)
- `ANALYZE_DURATION_OTHER` – analyzeduration for other protocols (default `20M`)
- `LIVE_FALLBACK_FPS` – still-frame refresh rate when live video fails (default `1`)
- `LIVE_MAX_FAILURES` – maximum consecutive ffmpeg failures before live view stops (default `10`)
- `LIVE_BACKOFF_MAX` – maximum seconds between live stream restart attempts (default `30`)
- `CHYRON_SPEED` – seconds the caption chyron scrolls; set to `0` to disable (default `0`)
- `DEFAULT_CLIP_DURATION` – seconds returned by the `/clip` endpoint when no `duration` query is provided (default `120`)
- `HEALTH_STATUS_ALWAYS_VISIBLE` – keep the System Performance icon visible even when the system is healthy (default `False`)
- `DISCOVERY_AUTOSTART` – run hourly background discovery automatically (default `False`)

## Watchdog Settings

The watchdog monitors process health and restarts Glimpser when repeated failures occur or resource limits are exceeded. Adjust these values if you encounter unnecessary restarts or need stricter checks.

- `WATCHDOG_FAILURE_THRESHOLD` – number of failed health checks before a restart is triggered (default `3`). Increase on flaky networks to avoid premature restarts.
- `WATCHDOG_RESTART_COOLDOWN` – cooldown period between restarts in seconds (default `900`). Increase this if restarts take significant time or if an external supervisor handles recovery.
- `WATCHDOG_MAX_FILE_HANDLES` – open file handle limit before triggering a restart (default `1000`). Lower when descriptor limits are tight or raise for high-load environments.
- `WATCHDOG_CPU_THRESHOLD` – CPU usage percentage that triggers open-file checks (default `80`). Adjust based on typical CPU load.
- `WATCHDOG_MEMORY_THRESHOLD` – memory usage percentage that triggers open-file checks (default `80`). Decrease on memory-constrained systems or increase when ample memory is available.

### Stealth Browser Defaults

Templates that enable `stealth` or `browser` mode require heavier page loads. If
`frequency` or `timeout` are omitted for such templates, Glimpser defaults to a
`frequency` of **60 minutes** and a `timeout` of **30 seconds** to reduce the
load on target sites and allow extra time for rendering.
These values are enforced by the TemplateManager so that even API clients that
skip validation adhere to the safer defaults.

## Advanced Options

Additional variables control AI behaviour and external tools:

- `LLM_MODEL_VERSION` – language model version to use (default `gpt-4.1-mini`). Supported models: `gpt-4.1-mini`, `gpt-4.1`, `gpt-4`
- `LLM_SUMMARY_PROMPT` – system prompt for log summaries. See [LLM Prompt Settings](llm_prompts.md)
  for the default text and `$datetime` token details.
- `LLM_CAPTION_PROMPT` – system prompt for image captions. Refer to
  [LLM Prompt Settings](llm_prompts.md) for examples and usage.
- `FFMPEG_PATH` – path to the `ffmpeg` binary (default `ffmpeg`)
- `GLIMPSER_AUTO_BUILD_FFMPEG` – set to `1` to build FFmpeg automatically when missing (default disabled)
- `FFPROBE_PATH` – path to the `ffprobe` binary (default `ffprobe`)
- `FFMPEG_HWACCEL` – hardware acceleration mode for ffmpeg (default `auto`).
  When set to `auto` Glimpser inspects available encoders and enables the first
  supported GPU method (`cuda`, `vaapi`, `qsv`, `v4l2m2m`) or falls back to
  software when none are detected.
- When hardware acceleration is enabled and Chrome supports OpenGL, Glimpser
  automatically launches Chrome with `--use-gl=egl` for improved GPU use.
- `FFMPEG_THREADS` – number of threads ffmpeg uses when encoding (default half the CPU cores)
- `CRAWLER_STARTUP_SPREAD` – minutes to stagger initial crawler runs at startup (default `10`)
- `CLIP_MODEL_NAME` – CLIP model used for object filtering (default `openai/clip-vit-base-patch32`)
  Example: `openai/clip-vit-large-patch14`
  This setting is read-only until Advanced Options are enabled.
- `CLIP_MODEL_PATH` – path to the ONNX model used for object filtering (default `models/clip-vit-b-32.onnx`). The runtime automatically selects CUDA or CPU providers when available. Non-macOS systems install `onnxruntime-gpu~=1.18` by default, while macOS falls back to the CPU-only `onnxruntime` package.
- `SCHEDULER_API_ENABLED` – toggle the APScheduler REST API (default `True`)

Refer to the code comments in `app/config.py` for full details on each setting.
