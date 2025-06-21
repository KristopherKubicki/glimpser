import { showSpinner, hideSpinner, showErrorIndicator } from "./video.js";

export function initTilePlayer() {
  const video = document.getElementById("live-video");
  if (!video) return;
  video.addEventListener("contextmenu", (e) => e.preventDefault());
  const source = video.querySelector("source");
  const camSelect =
    document.getElementById("camera-selector") ||
    document.getElementById("nav-camera-dropdown");

  // Ensure the synthetic "All" group exists so playback can default
  // to cycling through every camera when no specific selection is made.
  if (!window.templateDetails["All"]) {
    window.templateDetails["All"] = {
      groupCameras: Object.keys(window.templateDetails || {}),
    };
  }

  let current = camSelect && camSelect.value ? camSelect.value : "All";

  let abortCtl;
  let liveTimer;

  const container = video.parentElement;
  let spinner = container?.querySelector(".loading-spinner");
  if (!spinner && container) {
    spinner = document.createElement("div");
    spinner.className = "loading-spinner";
    spinner.setAttribute("aria-hidden", "true");
    container.appendChild(spinner);
  }

  const speedSlider = document.getElementById("speed-slider");
  const speedValue = document.getElementById("speed-value");
  let refreshSeconds = speedSlider
    ? Math.max(1, parseInt(speedSlider.value, 10) || 1)
    : 1;

  function updateSpeedLabel() {
    if (!speedValue || !speedSlider) return;
    const secs = Math.max(1, parseInt(speedSlider.value, 10) || 1);
    refreshSeconds = secs;
    speedValue.textContent =
      secs === 60 ? "1fpm" : `${(1 / secs).toFixed(2)}fps`;
    video.playbackRate = 1 / secs;
  }

  if (speedSlider) speedSlider.addEventListener("input", updateSpeedLabel);
  updateSpeedLabel();

  const image = document.createElement("img");
  image.id = "live-image";
  image.style.display = "none";
  if (container) container.appendChild(image);

  function showBounce() {
    if (!spinner) return;
    spinner.textContent = "\u25CF";
    spinner.classList.add("bouncy", "visible");
  }

  function hideBounce() {
    if (!spinner) return;
    spinner.classList.remove("bouncy", "visible");
  }

  const LIVE_CLASS = "live-mode";

  function playMjpg(target, isCamera = false) {
    if (!target) return;
    showSpinner(video);
    image.onload = () => hideSpinner(video);
    video.style.display = "none";
    image.style.display = "block";
    const param = isCamera ? "camera" : "group";
    const route = isCamera ? "/fast_stream.mjpg" : "/stream.mjpg";
    image.src = `${route}?${param}=${encodeURIComponent(target)}&time=${Date.now()}`;
    if (container) container.classList.add(LIVE_CLASS);
  }

  function scheduleLive(group) {
    clearTimeout(liveTimer);
    const onInteract = () => {
      clearTimeout(liveTimer);
      container.removeEventListener("mousemove", onInteract);
      container.removeEventListener("mousedown", onInteract);
      container.removeEventListener("touchstart", onInteract);
    };
    container.addEventListener("mousemove", onInteract);
    container.addEventListener("mousedown", onInteract);
    container.addEventListener("touchstart", onInteract);
    liveTimer = setTimeout(() => {
      container.removeEventListener("mousemove", onInteract);
      container.removeEventListener("mousedown", onInteract);
      container.removeEventListener("touchstart", onInteract);
      playMjpg(group);
    }, 2000);
  }

  async function loadHdClip() {
    const url = video.dataset.hdSrc;
    if (!url) return;
    if (abortCtl) abortCtl.abort();
    abortCtl = new AbortController();
    const timer = setTimeout(() => abortCtl.abort(), 10000);
    try {
      showSpinner(video);
      const res = await fetch(url, { signal: abortCtl.signal });
      clearTimeout(timer);
      hideSpinner(video);
      if (!res.ok) {
        showErrorIndicator(video);
        return;
      }
      const blob = await res.blob();
      const objUrl = URL.createObjectURL(blob);
      const pos = video.currentTime;
      const paused = video.paused;
      if (res.headers.get("X-Clip-Status") === "waiting") {
        showBounce();
        const onHide = () => hideBounce();
        video.addEventListener("canplay", onHide, { once: true });
        video.addEventListener("error", onHide, { once: true });
      }
      const onLoad = () => {
        video.currentTime = Math.min(pos, video.duration || pos);
        if (!paused) video.play().catch(() => {});
        URL.revokeObjectURL(objUrl);
      };
      video.addEventListener("loadedmetadata", onLoad, { once: true });
      if (source) source.src = objUrl;
      video.load();
    } catch (_) {
      hideSpinner(video);
      hideBounce();
      showErrorIndicator(video);
    }
  }

  // Switch the UI to live MJPEG playback immediately. Archived clips are
  // skipped entirely so the image element always shows the current stream.
  function play(name) {
    if (!name) return;
    current = name;
    hideBounce();
    if (name === "All") {
      playMjpg("all");
    } else if (name.startsWith("group-")) {
      playMjpg(name.slice(6));
    } else {
      playMjpg(name, true);
    }
  }

  if (camSelect) {
    camSelect.addEventListener("change", () => play(camSelect.value));
  }

  play(current);

  if (container) {
    const reset = () => {
      if (container.classList.contains(LIVE_CLASS)) {
        play(current);
      }
    };
    container.addEventListener("mousedown", reset);
    container.addEventListener("touchstart", reset);
  }
}

document.addEventListener("DOMContentLoaded", initTilePlayer);

export function updateCameraOptions(group) {
  const camSelect =
    document.getElementById("camera-selector") ||
    document.getElementById("nav-camera-dropdown");
  if (!camSelect) return;
  camSelect.innerHTML = "";
  if (!group || group === "all") {
    camSelect.style.display = "none";
    const opt = document.createElement("option");
    opt.value = "All";
    opt.textContent = "All";
    camSelect.appendChild(opt);
    camSelect.value = "All";
    return;
  }
  camSelect.style.display = "";
  const groupOpt = document.createElement("option");
  groupOpt.value = `group-${group}`;
  groupOpt.textContent = `Group: ${group}`;
  camSelect.appendChild(groupOpt);
  Object.entries(window.templateDetails || {})
    .filter(
      ([, det]) =>
        det.groups &&
        det.groups
          .split(",")
          .map((s) => s.trim())
          .includes(group),
    )
    .map(([cam]) => cam)
    .sort()
    .forEach((cam) => {
      const opt = document.createElement("option");
      opt.value = cam;
      opt.textContent = cam;
      camSelect.appendChild(opt);
    });
  camSelect.value = `group-${group}`;
}

export function changeGroup(group) {
  const navGroup = document.getElementById("nav-group-dropdown");
  if (!group) {
    group = navGroup ? navGroup.value : "all";
  }
  if (navGroup) navGroup.value = group;
  updateCameraOptions(group);
  const camSelect =
    document.getElementById("camera-selector") ||
    document.getElementById("nav-camera-dropdown");
  if (camSelect) camSelect.dispatchEvent(new Event("change"));
}

window.changeGroup = changeGroup;
window.updateCameraOptions = updateCameraOptions;
