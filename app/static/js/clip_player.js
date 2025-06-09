export function initClipPlayer(options = {}) {
  const {
    videoId = "live-video",
    posterId = "live-image",
    cameras = [],
    refresh = 60,
    playbackRate = 0.25,
  } = options;

  document.addEventListener("DOMContentLoaded", () => {
    const video = document.getElementById(videoId);
    if (!video) return;
    const posterEl = posterId ? document.getElementById(posterId) : null;
    let camList = cameras.slice();
    if (camList.length === 0) {
      const data = video.dataset.camera || "";
      if (data) camList = [data];
    }
    if (camList.length === 0) return;
    let index = 0;

    function updatePoster(cam) {
      if (!posterEl) return;
      const ts = Date.now();
      posterEl.src = `/last_screenshot/${cam}?t=${ts}`;
      video.poster = posterEl.src;
    }

    function playNext() {
      const cam = camList[index];
      const ts = Date.now();
      video.src = `/clip/${cam}?t=${ts}`;
      updatePoster(cam);
      video.load();
      video.playbackRate = playbackRate;
      const p = video.play();
      if (p && typeof p.catch === "function") {
        p.catch(() => {});
      }
      index = (index + 1) % camList.length;
    }

    video.addEventListener("ended", playNext);
    playNext();

    if (refresh > 0 && posterEl) {
      setInterval(
        () =>
          updatePoster(camList[(index + camList.length - 1) % camList.length]),
        refresh * 1000,
      );
    }
  });
}
