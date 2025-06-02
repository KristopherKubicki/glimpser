# Command Line Reference

This guide describes the available command line arguments for the main `glimpser` application, `generate_credentials.py`, and `app/config.py` when run as a script.

## glimpser (main.py)

The primary application script accepts the following options:

| Argument | Description |
| --- | --- |
| `--db-path` | Path to the SQLite database file. |
| `--host` | Host for the web server. |
| `--port` | Port for the web server. |
| `--log-path` | Path to the log file. |
| `--log-level` | Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`). |
| `--console-log` | Enable logging to the console. |
| `--debug` | Enable debug mode. |
| `--no-scheduler` | Disable the background scheduler. |
| `--no-watchdog` | Disable the watchdog thread. |
| `--screenshot-dir` | Directory for storing screenshots. |
| `--video-dir` | Directory for storing video files. |
| `--summaries-dir` | **Deprecated:** summaries are now stored in the database. |

## generate_credentials.py

This helper script creates or updates the credentials stored in the database.

| Argument | Description |
| --- | --- |
| `--db-path` | Path to the SQLite database file. |
| `--username` | Username for login. |
| `--password` | Password for login. |
| `--update-password` | Update only the password without modifying other settings. |
| `--secret-key` | Custom secret key; a new one is generated if not provided. |
| `--update-key` | Replace the stored secret key. |

## config.py

When invoked directly, `app/config.py` accepts a few path options to override the
defaults loaded from environment variables:

| Argument | Description |
| --- | --- |
| `--db-path` | Override the SQLite database location. |
| `--log-path` | Override the main log file path. |
| `--backup-path` | Override the configuration backup file. |

Use `--help` with any script to see these options from the command line.
