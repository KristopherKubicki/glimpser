export const NO_TIMESTAMP_PLACEHOLDER = "no timestamp";

export function timeAgo(dateString) {
  if (!dateString) return "just now";
  const now = new Date();
  const iso =
    dateString instanceof Date
      ? dateString.toISOString()
      : dateString.includes("T")
        ? /Z$|[+-]\d{2}:?\d{2}$/.test(dateString)
          ? dateString
          : `${dateString}Z`
        : `${dateString.replace(" ", "T")}Z`;
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) return "just now";
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
  const date =
    dateString instanceof Date
      ? dateString
      : new Date(
          dateString.includes("T")
            ? /Z$|[+-]\d{2}:?\d{2}$/.test(dateString)
              ? dateString
              : `${dateString}Z`
            : `${dateString.replace(" ", "T")}Z`,
        );
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
