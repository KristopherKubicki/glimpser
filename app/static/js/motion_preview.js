import { captureAge } from "./capture_age.js";

// One finite replay at a time. This never wakes a camera or starts a live encoder.
export function mountMotionPreview(camera, host, { autoCloseMs = 30000 } = {}) {
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
    objectUrl = null,
    ageTimer = null;
  const controller =
    typeof AbortController === "function" ? new AbortController() : null;
  const timeout = window.setTimeout(() => controller?.abort(), 10000);
  const lifetime = window.setTimeout(() => dispose(), autoCloseMs);
  function dispose() {
    if (disposed) return;
    disposed = true;
    controller?.abort();
    window.clearTimeout(timeout);
    window.clearTimeout(lifetime);
    window.clearInterval(ageTimer);
    image.removeAttribute("src");
    if (objectUrl) URL.revokeObjectURL(objectUrl);
    panel.remove();
  }
  close.addEventListener("click", dispose);
  fetch(`/event_buffer/${encodeURIComponent(camera)}.gif?recent=1`, {
    cache: "no-store",
    signal: controller?.signal,
  })
    .then(async (response) => {
      if (!response.ok) throw new Error("No recent replay");
      const start = Number(response.headers.get("X-Replay-Start"));
      const end = Number(response.headers.get("X-Replay-End"));
      const fps = Number(response.headers.get("X-Replay-Fps"));
      if (
        !start ||
        !end ||
        end < start ||
        Date.now() / 1000 - end > 30 ||
        end > Date.now() / 1000 + 5
      )
        throw new Error("Replay is too old");
      const blob = await response.blob();
      if (disposed) return;
      objectUrl = URL.createObjectURL(blob);
      image.src = objectUrl;
      image.hidden = false;
      label.textContent = "RECORDED REPLAY";
      const tick = () => {
        detail.textContent = `${Math.round(end - start)}s of footage · ended ${captureAge(new Date(end * 1000).toISOString())} · ${fps} fps measured`;
      };
      tick();
      ageTimer = window.setInterval(tick, 1000);
    })
    .catch(() => {
      if (disposed) return;
      label.textContent = "Replay unavailable";
      detail.textContent =
        "No fresh multi-frame recording. The saved image remains available.";
    })
    .finally(() => window.clearTimeout(timeout));
  return { dispose, panel };
}
