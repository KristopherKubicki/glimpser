export function captureAge(value, now = Date.now()) {
  if (!value) return "Awaiting capture";
  const raw = String(value).trim();
  const explicit = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(raw);
  const parsed = Date.parse(explicit ? raw : `${raw.replace(" ", "T")}Z`);
  if (!Number.isFinite(parsed)) return "Capture time unavailable";
  const seconds = Math.floor((now - parsed) / 1000);
  if (seconds < -60) return "Capture clock ahead";
  if (seconds < 10) return "just now";
  for (const [unit, size] of [
    ["day", 86400],
    ["hour", 3600],
    ["minute", 60],
    ["second", 1],
  ]) {
    if (seconds >= size) {
      const count = Math.floor(seconds / size);
      return `${count} ${unit}${count === 1 ? "" : "s"} ago`;
    }
  }
  return "just now";
}

export function sourceAge(freshness = {}, now = Date.now()) {
  const parts = [];
  if (freshness.low_light) parts.push("Dark camera frame");
  if (freshness.kind === "video_thumbnail") parts.push("Video thumbnail");
  if (freshness.waiting_for_browser)
    parts.push("Waiting for capture slot · Previous image retained");
  else if (freshness.source_unchanged)
    parts.push("Source checked; same image returned");
  else if (freshness.retained) parts.push("Previous image retained");
  if (freshness.capture_overdue) {
    parts.push("Saved capture overdue");
    if (freshness.last_attempt_at)
      parts.push(`Last attempt ${captureAge(freshness.last_attempt_at, now)}`);
  }
  if (freshness.clock_ahead) parts.push("Source clock ahead");
  else if (freshness.published_at)
    parts.push(`Source reports ${captureAge(freshness.published_at, now)}`);
  else if (freshness.inherited_at)
    parts.push(`Original capture ${captureAge(freshness.inherited_at, now)}`);
  if (freshness.unchanged_since) {
    const seconds = Number(freshness.unchanged_seconds);
    if (Number.isFinite(seconds) && seconds > 0) {
      const duration = captureAge(
        new Date(now - seconds * 1000).toISOString(),
        now,
      ).replace(/ ago$/, "");
      parts.push(`Source image unchanged for ≥ ${duration}`);
    } else {
      parts.push("Repeated source image; duration unknown");
    }
    if (freshness.checked_at)
      parts.push(`Last checked ${captureAge(freshness.checked_at, now)}`);
  }
  if (!freshness.published_at && !freshness.inherited_at)
    parts.push("Source time unknown");
  return parts.join(" · ");
}

export function sourceNeedsAttention(freshness = {}) {
  return Boolean(
    freshness.capture_overdue ||
      freshness.waiting_for_browser ||
      freshness.low_light ||
      freshness.retained ||
      freshness.older ||
      freshness.clock_ahead ||
      freshness.unchanged_since,
  );
}

// Pin screenshot bytes to the capture named by the UI. A concurrent newer
// capture must not change the image underneath an older timestamp label.
export function safeMediaUrl(value) {
  if (typeof value !== "string" || !value.trim()) return "";
  try {
    const url = new URL(value, window.location.href);
    if (url.protocol !== "http:" && url.protocol !== "https:") return "";
    return url.origin === window.location.origin
      ? url.pathname + url.search + url.hash
      : url.href;
  } catch {
    return "";
  }
}

export function captureImageUrl(base, captured) {
  base = safeMediaUrl(base);
  if (!base || !captured) return base;
  const url = new URL(base, window.location.href);
  if (!/^\/(?:clean_screenshot|last_screenshot)\//.test(url.pathname))
    return base;
  url.searchParams.set("capture", captured);
  return url.origin === window.location.origin
    ? url.pathname + url.search
    : url.href;
}

export function captionAge(value, now = Date.now()) {
  if (!value) return "Description time unknown";
  const age = captureAge(value, now);
  if (age === "Capture time unavailable") return "Description time unknown";
  if (age === "Capture clock ahead") return "Description clock ahead";
  return `Description generated ${age}`;
}
