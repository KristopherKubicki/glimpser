import { showSpinner, hideSpinner } from "./video.js";

export function initTilePlayer() {
  const video = document.getElementById("live-video");
  if (!video) return;
  const source = video.querySelector("source");
  const camSelect =
    document.getElementById("camera-selector") ||
    document.getElementById("nav-camera-dropdown");
  let current =
    camSelect?.value || Object.keys(window.templateDetails || {})[0];

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

  function playMjpg(group) {
    if (!group) return;
    video.style.display = "none";
    image.style.display = "block";
    image.src = `/stream.mjpg?group=${encodeURIComponent(group)}&time=${Date.now()}`;
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
      if (!res.ok) return;
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
    }
  }

  function play(name) {
    if (!name) return;
    current = name;
    video.style.display = "block";
    image.style.display = "none";

    if (name === "All") {
      if (source) source.src = "/last_teaser?group=all";
      video.setAttribute("data-hd-src", "/stream.mp4");
    } else if (name.startsWith("group-")) {
      const raw = name.slice(6);
      const group = encodeURIComponent(raw);
      if (source) source.src = `/last_teaser?group=${group}`;
      video.setAttribute("data-hd-src", `/stream.mp4?group=${group}`);
      scheduleLive(raw);
    } else {
      if (source) source.src = `/last_video/${name}`;
      video.setAttribute("data-hd-src", `/clip/${name}`);
    }

    video.load();
    hideBounce();
    loadHdClip();
  }

  if (camSelect) {
    camSelect.addEventListener("change", () => play(camSelect.value));
  }

  play(current);
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
