# Startup Tips and Gotchas

This page lists quick reminders that appear when Glimpser starts.

- **Running without HTTPS?** Set `SESSION_COOKIE_SECURE=False` in your environment so the login cookie works over plain HTTP:

  ```bash
  export SESSION_COOKIE_SECURE=False
  python main.py
  ```
- **Port already in use?** Make sure another process isn't bound to the configured port before starting Glimpser.
- **Need more logging?** Start the app with `--console-log` to mirror log output to your terminal.

Refer to this file any time you hit a startup issue.

## Startup Information Tables

The startup log now prints two tables. The first lists key configuration values
such as the host, port and whether the scheduler is enabled. The second table
shows current system metrics like CPU and memory usage. These summaries make it
easy to confirm everything is set up correctly before connecting to the web
interface.
