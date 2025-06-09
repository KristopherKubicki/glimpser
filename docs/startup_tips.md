# Startup Tips and Gotchas

This page lists quick reminders that appear when Glimpser starts.

- A retro ASCII banner highlights the version number at launch.
- **Running without HTTPS?** Set `SESSION_COOKIE_SECURE=False` in your environment so the login cookie works over plain HTTP:

  ```bash
  export SESSION_COOKIE_SECURE=False
  python main.py
  ```
- **Port already in use?** Make sure another process isn't bound to the configured port before starting Glimpser.
- **Need more logging?** Start the app with `--console-log` to mirror log output to your terminal.
- **Can't reach the server?** Binding `HOST` to `127.0.0.1` or `localhost` makes it invisible to other machines.

Refer to this file any time you hit a startup issue.

## Startup Information Tables

The startup log now prints two rich tables. The first lists important
configuration options including file paths and whether the scheduler,
watchdog and background crawlers are active. The second displays detailed
system metrics like open file count, uptime and whether GPU acceleration is
active. These summaries make it easy to confirm everything is set up correctly
before connecting to the web interface.
