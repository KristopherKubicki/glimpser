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

export function updateCameraOptions(group) {
  const camSelect = document.getElementById("camera-selector");
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

export function changeGroup() {
  const groupSelector = document.getElementById("group-selector");
  const group = groupSelector ? groupSelector.value : "all";
  const navGroup = document.getElementById("nav-group-dropdown");
  if (navGroup) navGroup.value = group;
  updateCameraOptions(group);
  const camSelect = document.getElementById("camera-selector");
  if (camSelect) camSelect.dispatchEvent(new Event("change"));
}

window.changeGroup = changeGroup;
window.updateCameraOptions = updateCameraOptions;
