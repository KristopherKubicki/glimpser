import {
  timeAgo,
  parseTimestamp,
  NO_TIMESTAMP_PLACEHOLDER,
} from "./time_utils.js";

export function isMobile() {
  return window.matchMedia("(max-width: 767px)").matches;
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
  const div = document.createElement("div");
  div.className = "templateDiv viewer-card";
  if (mobile) div.classList.add("mobile-card");
  div.dataset.name = name;
  div.dataset.index = String(index);
  div.dataset.last = template.last_screenshot_time || "";
  div.dataset.next = template.next_screenshot_time || "";
  div.dataset.error = template.capture_failed ? "1" : "0";

  const encoded = encodeURIComponent(name);
  const link = document.createElement("a");
  link.href = `/templates/${encoded}`;
  const media = document.createElement("div");
  media.className = "video-container camera-media";
  media.dataset.timestamp =
    template.last_screenshot_time || NO_TIMESTAMP_PLACEHOLDER;
  const captured = parseTimestamp(template.last_screenshot_time);
  const minutes = captured
    ? (Date.now() - captured.getTime()) / 60000
    : Infinity;
  const stale = minutes > Math.max(60, 3 * (Number(template.frequency) || 30));
  if (template.capture_failed || stale) media.classList.add("template-error");
  else media.classList.add("recent-screenshot");

  const title = document.createElement("div");
  title.className = "camera-name";
  title.textContent = name.replace(/([a-z])([A-Z])/g, "$1 $2");
  const still = document.createElement("img");
  still.className = "camera-still";
  still.src = `/last_screenshot/${encoded}`;
  still.alt = `${name} saved capture`;
  still.loading = "lazy";
  const video = document.createElement("video");
  video.dataset.name = name;
  video.dataset.poster = `/last_screenshot/${encoded}`;
  video.dataset.hdSrc = `/clip/${encoded}`;
  video.preload = "none";
  video.muted = true;
  video.playsInline = true;
  video.disableRemotePlayback = true;
  const source = document.createElement("source");
  source.src = `/last_video/${encoded}`;
  source.type = "video/mp4";
  video.append(source);
  video.addEventListener("loadeddata", () =>
    media.classList.add("has-preview-video"),
  );
  for (const event of ["error", "emptied"]) {
    video.addEventListener(event, () =>
      media.classList.remove("has-preview-video"),
    );
  }

  const state = document.createElement("div");
  state.className = "camera-freshness";
  const status = !captured
    ? "No capture"
    : stale
      ? "STALE snapshot"
      : template.capture_failed
        ? "Capture failed · saved snapshot"
        : "Snapshot";
  const age = document.createElement("span");
  age.dataset.humanTime = template.last_screenshot_time || "";
  age.textContent = captured
    ? timeAgo(template.last_screenshot_time)
    : "unavailable";
  state.append(document.createTextNode(`${status} · `), age);
  state.title = `Captured: ${template.last_screenshot_time || "never"}`;
  if (template.source_template) {
    const origin = document.createElement("span");
    origin.className = "camera-origin";
    origin.textContent = `View of ${template.source_template}`;
    state.append(origin);
  }
  const caption = document.createElement("div");
  caption.className = "caption-overlay";
  caption.textContent = template.last_caption || "No caption yet";
  caption.title = template.last_caption || "";
  const captionAge = document.createElement("span");
  captionAge.className = "camera-caption-age";
  captionAge.textContent = template.last_caption_time
    ? `Caption: ${timeAgo(template.last_caption_time)}`
    : "Caption unavailable";

  media.append(still, video, title, state, caption, captionAge);
  link.append(media);
  const open = document.createElement("a");
  open.href = `/live?camera=${encoded}`;
  open.className = "open-url-link";
  open.textContent = "Live";
  open.setAttribute("aria-label", `Open live view for ${name}`);
  div.append(link, open);
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
  if (templateList.dataset.wallLayout === "1") return;
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
