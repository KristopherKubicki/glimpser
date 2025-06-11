export function initTilePlayer() {
  const video = document.getElementById("live-video");
  if (!video) return;
  const source = video.querySelector("source");
  const camSelect = document.getElementById("camera-selector");
  let current =
    camSelect?.value || Object.keys(window.templateDetails || {})[0];

  let abortCtl;

  async function loadHdClip() {
    const url = video.dataset.hdSrc;
    if (!url) return;
    if (abortCtl) abortCtl.abort();
    abortCtl = new AbortController();
    const timer = setTimeout(() => abortCtl.abort(), 10000);
    try {
      const res = await fetch(url, { signal: abortCtl.signal });
      clearTimeout(timer);
      if (!res.ok) return;
      const blob = await res.blob();
      const objUrl = URL.createObjectURL(blob);
      const pos = video.currentTime;
      const paused = video.paused;
      const onLoad = () => {
        video.currentTime = Math.min(pos, video.duration || pos);
        if (!paused) video.play().catch(() => {});
        URL.revokeObjectURL(objUrl);
      };
      video.addEventListener("loadedmetadata", onLoad, { once: true });
      if (source) source.src = objUrl;
      video.load();
    } catch (_) {
      /* ignore */
    }
  }

  function play(name) {
    if (!name) return;
    current = name;
    if (source) source.src = `/last_video/${name}`;
    video.setAttribute("data-hd-src", `/clip/${name}`);
    video.load();
    loadHdClip();
  }

  if (camSelect) {
    camSelect.addEventListener("change", () => play(camSelect.value));
  }

  play(current);
}

document.addEventListener("DOMContentLoaded", initTilePlayer);
