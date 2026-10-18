import { captureAge } from "./capture_age.js";

// One finite replay at a time. This never wakes a camera or starts a live encoder.
export function mountMotionPreview(camera, host, { autoCloseMs = null } = {}) {
  const panel = document.createElement("section");
  panel.className = "motion-preview";
  panel.setAttribute("aria-label", `${camera} recent replay`);
  const header = document.createElement("header");
  const label = document.createElement("strong");
  label.textContent = "Loading recent replay…";
  const close = document.createElement("button");
  close.type = "button";
  close.textContent = "Close replay";
  const image = document.createElement("img");
  image.alt = `${camera} recorded replay`;
  image.hidden = true;
  const detail = document.createElement("p");
  detail.textContent = "Reading recent buffered frames.";
  header.append(label, close);
  panel.append(header, image, detail);
  host.append(panel);
  let disposed = false,
    failed = false,
    ready = false,
    objectUrl = null,
    ageTimer = null;
  const controller =
    typeof AbortController === "function" ? new AbortController() : null;
  const timeout = window.setTimeout(fail, 10000);
  let lifetime = window.setTimeout(() => dispose(), autoCloseMs ?? 30000);
  function releaseMedia() {
    controller?.abort();
    window.clearTimeout(timeout);
    window.clearInterval(ageTimer);
    image.onload = null;
    image.onerror = null;
    image.removeAttribute("src");
    image.hidden = true;
    if (objectUrl) URL.revokeObjectURL(objectUrl);
    objectUrl = null;
  }
  function dispose() {
    if (disposed) return;
    disposed = true;
    releaseMedia();
    window.clearTimeout(lifetime);
    window.removeEventListener("pagehide", dispose);
    document.removeEventListener("visibilitychange", handleVisibility);
    panel.remove();
  }
  function handleVisibility() {
    if (document.hidden) dispose();
  }
  function fail() {
    if (disposed || failed) return;
    failed = true;
    releaseMedia();
    label.textContent = "Replay unavailable";
    detail.textContent =
      "No fresh playable recording. The saved image remains available.";
  }
  window.addEventListener("pagehide", dispose);
  document.addEventListener("visibilitychange", handleVisibility);
  close.addEventListener("click", dispose);
  if (document.hidden) {
    dispose();
    return { dispose, panel };
  }
  Promise.resolve()
    .then(() =>
      disposed
        ? null
        : fetch(`/event_buffer/${encodeURIComponent(camera)}.gif?recent=1`, {
            cache: "no-store",
            signal: controller?.signal,
          }),
    )
    .then(async (response) => {
      if (disposed || failed) return;
      if (!response.ok) throw new Error("No recent replay");
      const start = Number(response.headers.get("X-Replay-Start"));
      const end = Number(response.headers.get("X-Replay-End"));
      const fps = Number(response.headers.get("X-Replay-Fps"));
      const frames = Number(response.headers.get("X-Replay-Frames"));
      const encodedDuration = response.headers.get("X-Replay-Duration");
      const duration = encodedDuration == null ? null : Number(encodedDuration);
      if (
        (duration !== null &&
          (!Number.isFinite(duration) || duration <= 0 || duration > 60)) ||
        ![start, end, fps, frames].every(Number.isFinite) ||
        start <= 0 ||
        end <= start ||
        end - start > 30 ||
        !Number.isInteger(frames) ||
        frames < 2 ||
        frames > 30 ||
        fps <= 0 ||
        fps > 30 ||
        Date.now() / 1000 - end > 30 ||
        end > Date.now() / 1000 + 5
      )
        throw new Error("Replay is too old");
      const blob = await response.blob();
      if (disposed || failed) return;
      objectUrl = URL.createObjectURL(blob);
      image.onload = () => {
        if (disposed || failed || ready) return;
        if (document.hidden) {
          dispose();
          return;
        }
        ready = true;
        image.onload = null;
        window.clearTimeout(timeout);
        image.hidden = false;
        label.textContent = "RECORDED REPLAY";
        const startedAt = performance.now();
        // Manual replay gets the complete clip after loading. Alerts retain
        // their caller-owned deadline and never extend the rotation hold.
        if (duration !== null && autoCloseMs === null) {
          window.clearTimeout(lifetime);
          lifetime = window.setTimeout(dispose, duration * 1000 + 2000);
        }
        const tick = () => {
          const elapsed = (performance.now() - startedAt) / 1000;
          const remaining =
            duration === null
              ? null
              : Math.max(0, Math.ceil(duration - elapsed));
          if (remaining === 0) {
            label.textContent = "Replay complete";
            window.clearInterval(ageTimer);
          }
          const playback =
            remaining === null
              ? ""
              : remaining > 0
                ? ` · ${remaining}s left`
                : " · final recorded frame";
          detail.textContent = `${Math.round(end - start)}s of footage · ended ${captureAge(new Date(end * 1000).toISOString())} · ${fps} fps measured${playback}`;
        };
        tick();
        ageTimer = window.setInterval(tick, 1000);
      };
      image.onerror = fail;
      image.src = objectUrl;
    })
    .catch(fail);
  return { dispose, panel };
}
