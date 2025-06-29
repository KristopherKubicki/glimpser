// Helpers for playing and switching video clips
export const CLIP_THROTTLE_MS = 30000;
let lastClipTime = 0;

/**
 * Play a video element and ignore abort/permission errors.
 * @param {HTMLMediaElement} el - Video or audio element.
 */
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

/**
 * Load a clip or stream source onto a video element.
 * @param {HTMLVideoElement} videoEl - Video element to update.
 * @param {string} cameraName - Target camera name.
 */
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
