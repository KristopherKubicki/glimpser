# Edit Template Preview

The edit template dialog now shows a mini live view of the camera in the top-right corner. This MJPEG stream lets you verify the feed while tweaking settings. The same preview appears on the **Settings → Discover** tab when adding a new camera so you can confirm the URL before saving.

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
