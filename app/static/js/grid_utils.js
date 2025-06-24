import { timeAgo, NO_TIMESTAMP_PLACEHOLDER } from "./time_utils.js";

export function isMobile() {
  return window.matchMedia("(hover: none) and (max-width: 767px)").matches;
}

export function computeBorderColor(ageMinutes, isError) {
  const base = isError ? [128, 128, 128] : [26, 115, 232];
  let step = 0;
  if (ageMinutes >= 1) {
    step = Math.floor(Math.log10(ageMinutes)) + 1;
  }
  const alpha = Math.pow(0.5, step);
  return `rgba(${base[0]}, ${base[1]}, ${base[2]}, ${alpha})`;
}

export function createTemplateCard(name, template, index, mobile) {
  const lastScreenshotTime =
    template.last_screenshot_time || NO_TIMESTAMP_PLACEHOLDER;
  const humanizedTimestamp =
    lastScreenshotTime === NO_TIMESTAMP_PLACEHOLDER
      ? NO_TIMESTAMP_PLACEHOLDER
      : timeAgo(lastScreenshotTime);
  const lastScreenshotDate = new Date(lastScreenshotTime);
  const ageMinutes = (Date.now() - lastScreenshotDate.getTime()) / 60000;
  const videoContainerClass = "video-container";
  const errorClass = template.capture_failed
    ? "template-error"
    : "recent-screenshot";
  const borderColor = computeBorderColor(ageMinutes, template.capture_failed);

  const div = document.createElement("div");
  div.classList.add("templateDiv");
  if (mobile) div.classList.add("mobile-card");
  div.style.opacity = "0";
  div.style.transform = "translateY(20px)";
  div.style.transition = "opacity 0.5s ease, transform 0.5s ease";

  div.dataset.name = name;
  div.dataset.index = index.toString();
  div.dataset.last = template.last_screenshot_time || "";
  div.dataset.next = template.next_screenshot_time || "";
  div.dataset.error = template.capture_failed ? "1" : "0";

  div.innerHTML = `
    <a href='/templates/${name}'>
      <div class="${videoContainerClass} ${errorClass}" data-timestamp="${lastScreenshotTime}" style="border-color: ${borderColor}">
        <div class="camera-name">${name}</div>
        <div class="loading-spinner" aria-hidden="true"></div>
        <video data-name="${name}" data-poster="/last_screenshot/${name}" alt="${name}" style="width:100%" muted title="${template.last_caption} (${humanizedTimestamp})" preload="none" disableRemotePlayback data-hd-src="/clip/${name}" loading="lazy">
          <source src="/last_video/${name}" type="video/mp4">
          Your browser does not support the video tag.
        </video>
        <div class="caption-overlay">${template.last_caption || ""}</div>
      </div>
    </a>
    <a href='${template.url}' target='_blank' class='open-url-link' title='Open monitored page' aria-label='Open monitored page'>↗</a>
    <button class='delete-camera-btn advanced-only' onclick="window.confirmDeleteCamera('${name}')" title='Delete this camera' aria-label='Delete camera'>✖</button>
  `;
  return div;
}

let captionsVisible = localStorage.getItem("showCaptions") !== "false";

export function setCaptionsVisibility(value) {
  const slider = document.getElementById("grid-width-slider");
  captionsVisible = value;
  localStorage.setItem("showCaptions", value.toString());
  applyCaptionVisibility(parseFloat(slider?.value || "0"));
  updateTableLayout(parseFloat(slider?.value || "0"));
}

export function getCaptionsVisibility() {
  return captionsVisible;
}

export function applyCaptionVisibility(width) {
  const templateList = document.getElementById("template-list");
  const captionToggle = document.getElementById("caption-toggle");
  const enabled = !width || width >= 150;
  const show = captionsVisible && enabled;
  document.documentElement.classList.toggle("hide-captions", !show);
  templateList
    ?.querySelectorAll(".caption-overlay")
    .forEach((o) => (o.style.display = show ? "block" : "none"));
  if (captionToggle) {
    captionToggle.classList.toggle("disabled", !enabled);
    captionToggle.classList.toggle("active", captionsVisible && enabled);
    captionToggle.classList.toggle("off", !captionsVisible && enabled);
    captionToggle.title = enabled
      ? captionsVisible
        ? "Hide caption overlays"
        : "Show caption overlays"
      : "Increase tile size to enable captions";
  }
}

export function updateTableLayout(width) {
  const rows = document.querySelectorAll("#camera-table .camera-row");
  rows.forEach((row) => {
    const preview = row.querySelector(".templateDiv");
    if (!preview) return;
    const height = preview.offsetHeight;
    row.style.height = `${height}px`;
    const caption = row.querySelector(".last-caption");
    const prompt = row.querySelector(".chat-prompt textarea");
    if (!caption || !prompt) return;
    caption.classList.toggle("hidden", width < 150);
    const available = height - prompt.offsetHeight - 10;
    const needsClamp = available < caption.scrollHeight;
    caption.style.maxHeight = needsClamp ? `${Math.max(available, 0)}px` : "";
    caption.classList.toggle("ellipsis", needsClamp);
  });
}

export function updateGridLayout() {
  const templateList = document.getElementById("template-list");
  if (!templateList) return;
  if (isMobile()) {
    templateList.style.gridTemplateColumns = "1fr";
  } else {
    templateList.style.gridTemplateColumns =
      "repeat(auto-fit, minmax(50px, var(--tile-size)))";
  }
}

export function setupTileResizeDrag(slider) {
  if (!slider) return;
  const handle = document.createElement("div");
  handle.id = "tile-drag-handle";
  document.body.appendChild(handle);

  let startX = 0;
  let startVal = 0;

  const onMove = (e) => {
    const clientX = e.touches ? e.touches[0].clientX : e.clientX;
    const dx = clientX - startX;
    const { width } = slider.getBoundingClientRect();
    const range = parseFloat(slider.max) - parseFloat(slider.min);
    const delta = (dx / width) * range;
    const value = Math.min(
      parseFloat(slider.max),
      Math.max(parseFloat(slider.min), startVal + delta),
    );
    slider.value = value.toString();
    slider.dispatchEvent(new Event("input"));
  };

  const endDrag = () => {
    document.removeEventListener("mousemove", onMove);
    document.removeEventListener("touchmove", onMove);
    document.removeEventListener("mouseup", endDrag);
    document.removeEventListener("touchend", endDrag);
  };

  const startDrag = (e) => {
    startX = e.touches ? e.touches[0].clientX : e.clientX;
    startVal = parseFloat(slider.value);
    document.addEventListener("mousemove", onMove);
    document.addEventListener("touchmove", onMove);
    document.addEventListener("mouseup", endDrag);
    document.addEventListener("touchend", endDrag);
    e.preventDefault();
  };

  handle.addEventListener("mousedown", startDrag);
  handle.addEventListener("touchstart", startDrag);
}
