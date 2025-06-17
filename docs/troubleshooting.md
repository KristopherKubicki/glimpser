# Troubleshooting Guide for Glimpser

This guide addresses common issues that users might encounter while using Glimpser and provides solutions.

## 1. Installation Issues

### Problem: Dependencies fail to install

-**Solution:**

- Ensure you're using Python 3.8 or newer (tested up to 3.13): `python --version`
- Update pip: `pip install --upgrade pip`
- If you're on Windows, make sure you have the necessary C++ build tools installed for certain packages.
- Double-check that you're working in the correct virtual environment.
- Review the output of the install command for missing system libraries.

## 2. Configuration Issues

### Problem: Can't connect to data sources

**Solution:**

- Check your internet connection
- Verify the URL of the data source
- Ensure you have the necessary permissions to access the data source
- Check if the data source requires authentication
- Ensure your `.env` file is loaded if you rely on environment variables

### Problem: API key not working

**Solution:**

- Regenerate your API key in the Glimpser web interface
- Ensure you're using the correct API key format in your requests

### Problem: Invalid proxy values

**Solution:**

- Ensure the proxy string begins with `http://` or `https://`.
- Blank or malformed proxy values are ignored by Glimpser.

## 3. Performance Issues

### Problem: High CPU usage

**Solution:**

- Reduce the number of concurrent data sources
- Increase the refresh interval for less critical sources
- Check the `MAX_WORKERS` setting and adjust if necessary
- Increase `CRAWLER_STARTUP_SPREAD` to stagger camera startup more gently
- Open the _Status_ tab under Settings to watch CPU and memory usage in real time

### Problem: Out of memory errors

**Solution:**

- Reduce the `MAX_RAW_DATA_SIZE` setting
- Increase the system's available memory
- Consider using a database instead of in-memory storage for large datasets
- Lower the capture resolution or frame rate if possible

## 4. Data Processing Issues

### Problem: Inaccurate or missing captions

**Solution:**

- Check the `LLM_CAPTION_PROMPT` setting and adjust if necessary
- Ensure your CHATGPT_KEY is valid and has sufficient credits
- Leave `CHATGPT_KEY` empty to disable ChatGPT features gracefully
- Verify that the image data is being correctly captured and processed

### Problem: Summaries not generating

**Solution:**

- Check the `LLM_SUMMARY_PROMPT` setting
- Ensure there's enough data collected to generate a meaningful summary
- Verify that the CHATGPT_KEY is working correctly
- Confirm the scheduler is running and you did not start the app with
  `--no-scheduler`
- Visit `/jobs` to ensure the `summary` job is listed and check
  `logs/glimpser.log` for errors

## 5. Web Interface Issues

### Problem: Web interface not loading

**Solution:**

- Check if the Glimpser server is running
- Verify you're using the correct port (default is 8082)
- Ensure the `HOST` setting is `0.0.0.0` so the server is reachable from other devices
- Clear your browser cache and cookies
- Confirm that WebSocket connections are allowed on your network

### Problem: Can't log in to the web interface

**Solution:**

- Ensure you're using the correct username and password
- Verify that the account exists in the `users` table
- Try resetting your password through the recovery process
- Repeated failures trigger a 24-hour lockout and display a
  "Too many failed attempts" message
- Invalid credentials now generate on-screen feedback and are logged
- If you land back on the login page without errors, check that cookies are
  enabled. The page shows a "Login requires cookies" warning when the session
  cookie is missing. Running without HTTPS? Disable `SESSION_COOKIE_SECURE` so
  your browser accepts the cookie. See [Startup Tips](startup_tips.md) for a
  quick reminder of this and other common gotchas.

## Getting Further Help

If you're still experiencing issues after trying these solutions, please:

1. Check our [FAQ](faq.md) for more information
2. Search for similar issues in our [GitHub Issues](https://github.com/KristopherKubicki/glimpser/issues)
3. Post a new issue on GitHub with detailed information about your problem
4. Reach out to our community support forum for assistance

Remember to always include relevant log files, error messages, and your Glimpser version when seeking help.

## 6. Database Issues

### Problem: Unable to connect to the database

**Solution:**

- Ensure the database path in `GLIMPSER_DB` is correct.
- Check file permissions so the process can read and write to the database.
- For remote servers verify network connectivity and credentials.

### Problem: Database locked errors

**Solution:**

- Stop other Glimpser instances that might be using the same database file.
- If using SQLite, ensure the volume is mounted with proper locking support.
- Consider switching to a server database like PostgreSQL for multi‑user setups.
- Glimpser now enables SQLite WAL mode at startup which reduces lock errors.
  Remove any stale `-journal` files if they remain from older runs.

## 7. Docker Deployment Issues

### Problem: Containers fail to start

**Solution:**

- Build images again with `docker compose build --no-cache`.
- Inspect the container logs with `docker compose logs` for errors.
- Confirm that environment variables in `docker-compose.yaml` match your setup.

### Problem: Port conflicts

**Solution:**

- Make sure no other service is using port 8082.
- Glimpser now prints which process is using the port when startup fails.
- You can still run `lsof -i :8082` or `fuser -n tcp 8082` manually.
- Change the `ports` mapping in `docker-compose.yaml` if needed.

### Problem: Permission denied on volumes

**Solution:**

- Verify that the host directories mapped as volumes are writable by Docker.
- On Linux you may need to adjust ownership with `chown` or use Docker's `user` option.

## 8. Environment Variable Issues

### Problem: Settings not loading

**Solution:**

- Confirm variables are defined in your shell or `.env` file before starting.
- Use `printenv | grep GLIMPSER` to check that values are present.

### Problem: Missing secrets

**Solution:**

- Ensure `CHATGPT_KEY` and any other credentials are exported in your environment.
- When running under Docker, set these values in `docker-compose.yaml`.

## 9. Logging and Debugging Tips

Glimpser writes logs to the console and exposes them via the _Status_ tab. If something goes wrong:

- Use the **System Monitoring and Logs** guide to access live logs.
- Increase the `LOG_LEVEL` or `FLASK_LOG_LEVEL` environment variable to `DEBUG` for more details.
- Review recent entries for stack traces or connection errors.
- If logs show "Failed to open last shot ... invalid image", the screenshot file
  is corrupted. Delete the file so a new capture can replace it.

## 10. Upgrade Issues

### Problem: Errors after pulling a new version

**Solution:**

- Run `pip install . --upgrade` to update dependencies from `pyproject.toml`.
- Apply any new database migrations as described in the release notes.
- The `capture_failed` column is added automatically if missing.
- Clear your browser cache to avoid stale JavaScript files.

### Problem: Search bar does not filter templates

**Solution:**

- Ensure you are running the latest Glimpser version.
- Refresh the page to load the updated JavaScript.

## 11. Live View Problems

### Problem: Live page never loads a frame

If the logs repeat messages like `No frames captured from stream` or
`Error capturing frame with ffmpeg`, the camera URL may point to a
snapshot image rather than a true video stream.

**Solution:**

- Use the camera's RTSP or HTTP video stream URL when available.
- Snapshot-only URLs now fall back to an MJPEG feed so the live view
  behaves like a regular video stream.
- If playback fails entirely, the viewer now shows the last captured
  screenshot so the page is never blank.
- HTTP errors like `403 Forbidden` or repeated ffmpeg timeouts typically mean
  the stream is blocked. Verify the URL is accessible from the host running
  Glimpser and check for required credentials or firewall rules.
- When ffmpeg repeatedly fails, retries now back off exponentially up to
  `LIVE_MAX_RETRY_DELAY` seconds so the server isn't hammered.
- Some cameras reject ffmpeg if it does not send browser-style headers. The
  live stream now includes the configured `UA`, `referer` and `origin` headers.
  Adjust these settings if your camera expects a specific user agent.
- The server now checks connectivity with a HEAD request before starting
  `ffmpeg`. When the camera is offline the live view waits and retries
  instead of immediately spawning a process that will fail.
- When ffmpeg repeatedly fails, the server now waits progressively longer
  between restart attempts to reduce log noise.

### Problem: Playback continues in the background after switching types

Older versions kept preloading the previous stream when you changed the video
source. That could cause extra network requests and confusing behavior.

**Solution:**

- Update to the latest version.
- The player now destroys any active HLS or looping handlers before starting the
  new stream, so switching sources cleanly stops the old one.

### Problem: Cameras keep loading after leaving the dashboard

Thumbnail players could keep downloading clips after you navigate away.

**Solution:**

- Update to the latest version.
- Background preloading now stops when the tab loses focus.

### Problem: Loop video or the "All" camera shows `Format error`

This typically happens when Glimpser cannot locate a recent MP4 clip for a
camera. The player attempts to load the file and the browser reports a
_Format error_ because the response is missing or invalid. The server now
falls back to a blank clip so playback never fails entirely. The filler
video matches the resolution of the latest footage, ensuring subsequent
concatenation succeeds.

**Solution:**

- Ensure the `compile_to_teaser` job is running so group videos are generated.
- When a clip fails to load, the live player now skips to the next camera
  instead of stalling on the error message.

### Problem: "All" PNG stream always shows "No screenshot available"

The live viewer requests `/stream.png` to display the most recent frame from any
camera. If the newest PNG is corrupt or missing the placeholder image is shown
instead.

**Solution:**

- Ensure each camera is capturing screenshots in `data/screenshots`.
- Remove any zero-byte or invalid PNG files. Glimpser now skips corrupt images
  when choosing the latest shot.
- Use `/take_screenshot/<camera>` to capture a fresh frame if needed.

## 12. Layout Issues

### Problem: Buttons at the bottom of the Templates page are hidden

The footer uses a fixed position at the bottom of the screen. On long pages this
could overlap the last buttons. The site now calculates the footer height and
sets a `--footer-space` CSS variable so mobile views always leave enough room.

**Solution:**

- Glimpser now adds extra padding to the `main` element so page content scrolls
  fully above the footer. Update to the latest version or mimic this logic in
  your custom CSS.

## 13. Camera Discovery Issues

### Problem: Discovery page times out or stops on "Scanning SSDP"

**Solution:**

- Networks with many SSDP devices can delay this step. Wait a little longer or restrict scanning using the network dropdown (e.g., `192.168.1.0/24`).
- Since v0.9.1 SSDP scanning stops after five seconds so discovery continues even on busy networks.
- Ensure UDP multicast traffic is allowed; blocked multicast causes timeouts.
- Check `logs/glimpser.log` for `SSDP probe error` messages if the scan never finishes.

## 14. Shutdown Issues

### Problem: Threads remain alive when exiting Glimpser

If shutdown is interrupted it can leave background threads running.

**Solution:**

- Glimpser now manages cleanup through `CleanupManager`, ensuring shutdown only runs once.
- Calling `main.shutdown_manager.cleanup()` manually will join any remaining threads.
- If threads still refuse to exit, call `app.utils.scheduling.stop_background_tasks()` to signal the
  metrics and logging loops to terminate.

## 15. Display Connection Errors

### Problem: "pynput not available" or "failed to acquire X connection"

This happens when Glimpser cannot open an X display. The optional
`pynput` package enables activity detection; when missing, the
application simply logs the failure and continues. The logs may show
`Maximum number of clients reached` or `Can't connect to display`.

**Solution:**

- Ensure an X server is running and `$DISPLAY` points to it.
- Close stray X applications or restart the display if the client limit is hit.
- On headless systems run Glimpser with `xvfb-run` to start a temporary virtual display, e.g.
  `xvfb-run --server-args="-screen 0 1280x720x24" python main.py`.
- If the connection still fails, Glimpser will log the error and skip activity detection so the server stays online.
