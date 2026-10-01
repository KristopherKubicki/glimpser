// Household time is independent of the displayed camera, source age, and network.
const mounted = new WeakMap();
export function clockParts(now = new Date()) {
  const options = { timeZone: "America/Chicago" };
  return {
    time: new Intl.DateTimeFormat("en-US", {
      ...options,
      hour: "numeric",
      minute: "2-digit",
      hour12: true,
    }).format(now),
    date: new Intl.DateTimeFormat("en-US", {
      ...options,
      weekday: "short",
      month: "short",
      day: "numeric",
    }).format(now),
    zone: new Intl.DateTimeFormat("en-US", {
      ...options,
      timeZoneName: "short",
    })
      .formatToParts(now)
      .find((part) => part.type === "timeZoneName").value,
  };
}

export function mountAmbientClock(host, mode = "room") {
  if (!host) return () => {};
  if (mounted.has(host)) return mounted.get(host);
  if (!document.querySelector("link[data-ambient-clock-style]")) {
    const link = document.createElement("link");
    link.rel = "stylesheet";
    link.href = "/static/css/ambient_clock.css?v=20260922-2";
    link.dataset.ambientClockStyle = "";
    document.head.append(link);
  }
  const clock = document.createElement("div");
  clock.className = `ambient-clock ambient-clock--${mode}`;
  const label = document.createElement("span");
  label.className = "ambient-clock-label";
  const time = document.createElement("time");
  const date = document.createElement("span");
  date.className = "ambient-clock-date";
  clock.append(label, time, date);
  host.append(clock);
  // Reserve layout space in the active text panel instead of covering pixels.
  const place = () => {
    if (mode !== "room") return;
    const target =
      host.querySelector(".kiosk-offline-caption") ||
      host.querySelector(".rotation-overview > header") ||
      host.querySelector(
        ".landing-scene.is-visible.has-kiosk-live .kiosk-live-label",
      ) ||
      host.querySelector(".landing-scene.is-visible .kiosk-timelapse-label") ||
      host.querySelector(".landing-scene.is-visible .kiosk-caption-strip");
    if (target) {
      if (clock.parentElement !== target) target.append(clock);
      if (clock.hidden) clock.hidden = false;
    } else if (!clock.hidden) clock.hidden = true;
  };
  const observer =
    mode === "room" && typeof MutationObserver === "function"
      ? new MutationObserver(place)
      : null;
  observer?.observe(host, {
    childList: true,
    subtree: true,
    attributes: true,
    attributeFilter: ["class"],
  });
  place();
  const update = () => {
    const now = new Date();
    const parts = clockParts(now);
    label.textContent = `NOW · ${parts.zone}`;
    time.textContent = parts.time;
    time.dateTime = now.toISOString();
    date.textContent = parts.date;
    clock.setAttribute(
      "aria-label",
      `Current Chicago time: ${parts.time}, ${parts.date}, ${parts.zone}`,
    );
  };
  update();
  const timer = window.setInterval(update, 1000);
  document.addEventListener("visibilitychange", update);
  const dispose = () => {
    observer?.disconnect();
    window.clearInterval(timer);
    document.removeEventListener("visibilitychange", update);
    window.removeEventListener("pagehide", dispose);
    clock.remove();
    mounted.delete(host);
  };
  window.addEventListener("pagehide", dispose, { once: true });
  mounted.set(host, dispose);
  return dispose;
}
