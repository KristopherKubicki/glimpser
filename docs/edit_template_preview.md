# Edit Template Preview

The edit template dialog shows a mini live view of the camera in the top-right corner with a quick summary of the URL, capture mode, and schedule. This MJPEG stream lets you verify the feed while tweaking settings, while the summary updates as you change fields so you can sanity-check the setup at a glance. The same preview appears on the **Settings → Discover** tab when adding a new camera so you can confirm the URL before saving.

The editor now highlights required fields, adds quick capture presets, and includes a direct URL test button. Use the capture mode toggles to switch between direct stream and browser workflows; advanced settings expand below for XPaths, callbacks, and authentication.

Advanced options include several checkboxes with expanded tooltips:

- **Browser** – launch a full browser for dynamic pages or when you need to
  supply popup or dedicated XPaths. Leave this disabled for raw video streams;
  XPath fields are ignored when the source is a video.
- **Headless** – hide the browser window during capture. Turn it off when
  debugging a login flow so you can watch the page load.
- **Stealth** – mask automation to bypass simple bot checks. It increases start
  up time but helps on sites that block headless browsers.
- **Dark Mode** – force a dark theme when the browser supports it. This has no
  effect on direct video feeds.
- **Invert** – flip the colors of the captured frame. Useful for infrared or
  high‑contrast scenes.
