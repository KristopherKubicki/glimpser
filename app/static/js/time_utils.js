export const NO_TIMESTAMP_PLACEHOLDER = "no timestamp";

function scoreTimestampCandidate(nowMs, candidate) {
  const diffMs = nowMs - candidate.getTime();
  // Prefer plausible past timestamps. Penalize future timestamps heavily so
  // mixed local/UTC strings resolve to whichever interpretation is closer
  // to "now" without claiming stale captures are many hours old.
  return diffMs >= 0 ? diffMs : Math.abs(diffMs) + 7 * 24 * 60 * 60 * 1000;
}

export function parseTimestamp(dateString) {
  if (!dateString) return null;
  if (dateString instanceof Date) {
    return Number.isNaN(dateString.getTime()) ? null : dateString;
  }

  if (typeof dateString === "number") {
    const millis =
      Number.isFinite(dateString) && dateString < 1e12
        ? dateString * 1000
        : dateString;
    const parsed = new Date(millis);
    return Number.isNaN(parsed.getTime()) ? null : parsed;
  }

  const raw = String(dateString).trim();
  if (!raw) return null;

  const nowMs = Date.now();
  const candidates = [];
  const seen = new Set();
  const addCandidate = (value) => {
    const key = String(value);
    if (seen.has(key)) return;
    seen.add(key);
    const parsed = new Date(value);
    if (!Number.isNaN(parsed.getTime())) {
      candidates.push(parsed);
    }
  };

  if (/^\d{10,13}$/.test(raw)) {
    addCandidate(Number(raw));
  }

  const hasTimezone = /Z$|[+-]\d{2}:?\d{2}$/.test(raw);
  if (raw.includes("T")) {
    if (hasTimezone) {
      addCandidate(raw);
    } else {
      // Try both local and UTC when timezone is missing.
      addCandidate(raw);
      addCandidate(`${raw}Z`);
    }
  } else {
    const normalized = raw.replace(" ", "T");
    addCandidate(raw);
    addCandidate(normalized);
    if (!hasTimezone) {
      addCandidate(`${normalized}Z`);
    }
  }

  if (!candidates.length) return null;

  let best = candidates[0];
  let bestScore = scoreTimestampCandidate(nowMs, best);
  for (let i = 1; i < candidates.length; i += 1) {
    const score = scoreTimestampCandidate(nowMs, candidates[i]);
    if (score < bestScore) {
      best = candidates[i];
      bestScore = score;
    }
  }
  return best;
}

export function timeAgo(dateString) {
  if (!dateString) return "just now";
  const now = Date.now();
  const parsed = parseTimestamp(dateString);
  if (!parsed) return "just now";
  const diffInSeconds = Math.floor((now - parsed) / 1000);
  if (diffInSeconds < 0) return "in the future";

  const intervals = [
    { label: "year", short: "y", seconds: 31536000 },
    { label: "month", short: "mo", seconds: 2592000 },
    { label: "day", short: "d", seconds: 86400 },
    { label: "hour", short: "h", seconds: 3600 },
    { label: "minute", short: "m", seconds: 60 },
    { label: "second", short: "s", seconds: 1 },
  ];

  for (const { short, seconds } of intervals) {
    const count = Math.floor(diffInSeconds / seconds);
    if (count >= 1) return `${count}${short} ago`;
  }
  return "just now";
}

export function formatExactTime(dateString) {
  const date = parseTimestamp(dateString);
  if (!date) return String(dateString || "");
  return date.toString();
}

export function updateHumanizedTimes() {
  document.querySelectorAll(".humanized-time").forEach((element) => {
    const timestamp = element.getAttribute("data-time");
    if (timestamp) {
      element.textContent = timeAgo(timestamp);
      element.title = formatExactTime(timestamp);
    }
  });

  document
    .querySelectorAll(
      ".video-container[data-timestamp], .templateDiv img[data-timestamp], video.hover-video[data-timestamp]",
    )
    .forEach((element) => {
      const original =
        element.dataset.originalTimestamp ||
        element.getAttribute("data-timestamp");
      if (!element.dataset.originalTimestamp) {
        element.dataset.originalTimestamp = original;
      }
      if (original && original !== NO_TIMESTAMP_PLACEHOLDER) {
        element.setAttribute("data-timestamp", timeAgo(original));
        element.setAttribute("title", formatExactTime(original));
      } else if (original === NO_TIMESTAMP_PLACEHOLDER) {
        element.setAttribute("data-timestamp", NO_TIMESTAMP_PLACEHOLDER);
        element.removeAttribute("title");
      }
    });
}
