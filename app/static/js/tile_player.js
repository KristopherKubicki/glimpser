export function initTilePlayer() {
  const video = document.getElementById("live-video");
  if (!video) return;
  const source = video.querySelector("source");
  const camSelect = document.getElementById("camera-selector");
  let current =
    camSelect?.value || Object.keys(window.templateDetails || {})[0];

  function play(name) {
    if (!name) return;
    current = name;
    if (source) source.src = `/last_video/${name}`;
    video.setAttribute("data-hd-src", `/clip/${name}`);
    video.load();
  }

  if (camSelect) {
    camSelect.addEventListener("change", () => play(camSelect.value));
  }

  play(current);
}

document.addEventListener("DOMContentLoaded", initTilePlayer);
