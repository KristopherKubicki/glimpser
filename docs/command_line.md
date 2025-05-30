# Command Line Reference

This guide describes the available command line arguments for the main `glimpser` application and the `generate_credentials.py` utility.

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
| `--summaries-dir` | Directory for storing summaries. |

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

Use `--help` with either script to see these options from the command line.
