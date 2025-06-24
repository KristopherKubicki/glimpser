export const CLIP_THROTTLE_MS = 30000;
let lastClipTime = 0;

export function safePlay(el) {
  const promise = el.play();
  if (promise && typeof promise.catch === "function") {
    promise.catch((err) => {
      if (err.name !== "AbortError" && err.name !== "NotAllowedError") {
        console.error("Error playing video:", err);
      }
    });
  }
}

export function setClipSrc(videoEl, cameraName) {
  const now = Date.now();
  if (now - lastClipTime >= CLIP_THROTTLE_MS) {
    videoEl.src = `/clip/${cameraName}`;
    lastClipTime = now;
  } else {
    videoEl.src = `/stream.mp4?camera=${encodeURIComponent(cameraName)}`;
  }
  videoEl.load();
  safePlay(videoEl);
}
