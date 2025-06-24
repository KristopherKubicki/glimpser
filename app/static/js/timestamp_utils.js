import { timeAgo, formatExactTime } from "./templates.js";

export function updateFrameTimestamp(details, camera) {
  const container = document.querySelector(".video-container");
  if (!container) return;
  const info = details[camera];
  if (!info || !info.last_screenshot_time) {
    container.removeAttribute("data-timestamp");
    container.removeAttribute("title");
    return;
  }
  container.dataset.originalTimestamp = info.last_screenshot_time;
  container.setAttribute("data-timestamp", timeAgo(info.last_screenshot_time));
  container.setAttribute(
    "title",
    info.last_caption
      ? `${formatExactTime(info.last_screenshot_time)} - ${info.last_caption}`
      : formatExactTime(info.last_screenshot_time),
  );
}

export function setTimestampVisibility(details, camera, show) {
  const container = document.querySelector(".video-container");
  if (!container) return;
  if (show) {
    updateFrameTimestamp(details, camera);
  } else {
    container.removeAttribute("data-timestamp");
  }
}
