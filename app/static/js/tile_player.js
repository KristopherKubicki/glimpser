import { showSpinner, hideSpinner } from "./video.js";

export function initTilePlayer() {
  const video = document.getElementById("live-video");
  if (!video) return;
  const source = video.querySelector("source");
  const camSelect = document.getElementById("camera-selector");
  let current =
    camSelect?.value || Object.keys(window.templateDetails || {})[0];

  let abortCtl;

  const container = video.parentElement;
  let spinner = container?.querySelector(".loading-spinner");
  if (!spinner && container) {
    spinner = document.createElement("div");
    spinner.className = "loading-spinner";
    spinner.setAttribute("aria-hidden", "true");
    container.appendChild(spinner);
  }

  function showBounce() {
    if (!spinner) return;
    spinner.textContent = "\u25CF";
    spinner.classList.add("bouncy", "visible");
  }

  function hideBounce() {
    if (!spinner) return;
    spinner.classList.remove("bouncy", "visible");
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
    if (source) source.src = `/last_video/${name}`;
    video.setAttribute("data-hd-src", `/clip/${name}`);
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
