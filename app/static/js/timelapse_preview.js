import { captureAge } from "./capture_age.js";

export const TIMELAPSE_INTERVAL_MS = 60000;
export const TIMELAPSE_PRELOAD_LEAD_MS = 12000;

// Keep both initial playback and later opportunities independent of page uptime.
export function timelapseIsDue(lastPlayedAt, now = Date.now()) {
  return lastPlayedAt === null || now - lastPlayedAt >= TIMELAPSE_INTERVAL_MS;
}

let prepared = null;
const lastReplay = new Set();

export function preferCurrentView(
  historyDue,
  lastHistoryAttempt,
  lastLive,
  priority,
) {
  if (priority || !historyDue) return true;
  return (
    lastHistoryAttempt !== null &&
    (lastLive === null || lastHistoryAttempt > lastLive)
  );
}

export function createHistoryMemory() {
  const shown = new Map();
  return {
    repeats(camera, start, end, now = Date.now()) {
      const prior = shown.get(camera);
      // Small additions to the same history do not make a useful new review.
      return Boolean(
        prior &&
          now - prior.at < 10 * 60 * 1000 &&
          Math.abs(start - prior.start) < 300 &&
          Math.abs(end - prior.end) < 300,
      );
    },
    remember(camera, start, end, now = Date.now()) {
      shown.delete(camera);
      shown.set(camera, { start, end, at: now });
      if (shown.size > 128) shown.delete(shown.keys().next().value);
    },
  };
}
const historyMemory = createHistoryMemory();

// Only one upcoming clip is fetched; failed preloads never affect rotation.
export function preloadTimelapse(camera) {
  if (!camera || typeof AbortController !== "function") return;
  if (prepared?.camera === camera && prepared.expires > Date.now()) return;
  prepared?.controller?.abort();
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 8000);
  prepared = {
    camera,
    controller,
    expires: Date.now() + 30000,
    response: Promise.resolve()
      .then(() =>
        fetch(`/timelapse/${encodeURIComponent(camera)}.gif`, {
          cache: "no-store",
          signal: controller.signal,
        }),
      )
      .then(async (response) => {
        if (!response?.ok) return null;
        const blob = await response.blob();
        return { ok: true, headers: response.headers, blob: async () => blob };
      })
      .catch(() => null)
      .finally(() => window.clearTimeout(timeout)),
  };
}

// A missing timelapse never advances rotation or changes the accepted still.
export function mountTimelapse(camera, scene, { onReady = () => {} } = {}) {
  const host = scene.querySelector(".landing-hero-media");
  let disposed = false,
    objectUrl = null,
    lifetime = null,
    ageTimer = null,
    fadeTimer = null;
  const controller =
    typeof AbortController === "function" ? new AbortController() : null;
  const node = document.createElement("div");
  node.className = "kiosk-timelapse";
  const image = document.createElement("img");
  image.alt = `${camera} recorded timelapse`;
  const label = document.createElement("div");
  label.className = "kiosk-timelapse-label";
  const title = document.createElement("strong");
  title.textContent = `${camera} · RECORDED HISTORY`;
  const detail = document.createElement("span");
  const playback = document.createElement("span");
  const progress = document.createElement("progress");
  progress.setAttribute("aria-label", "Recorded clip playback");
  progress.max = 1;
  progress.value = 0;
  const next = document.createTextNode("");
  playback.append(progress, next);
  label.append(title, detail, playback);
  node.append(image, label);
  const dispose = () => {
    if (disposed) return;
    disposed = true;
    controller?.abort();
    window.clearTimeout(timeout);
    window.clearTimeout(lifetime);
    window.clearTimeout(fadeTimer);
    window.clearInterval(ageTimer);
    image.onload = null;
    image.onerror = null;
    image.removeAttribute("src");
    node.remove();
    scene.classList.remove("has-timelapse");
    if (objectUrl) URL.revokeObjectURL(objectUrl);
  };
  const timeout = window.setTimeout(dispose, 8000);
  if (!host) {
    dispose();
    return { dispose };
  }
  // Alternate available buffered cameras between recent action and long history.
  // One shared deadline bounds both attempts; no failure advances the rotation.
  const preferReplay =
    scene.dataset.heroReplayAvailable === "true" && !lastReplay.has(camera);
  const takeTimelapse = () => {
    const request =
      prepared?.camera === camera && prepared.expires > Date.now()
        ? prepared.response
        : fetch(`/timelapse/${encodeURIComponent(camera)}.gif`, {
            cache: "no-store",
            signal: controller?.signal,
          });
    if (prepared?.camera === camera) prepared = null;
    return request;
  };
  // A camera without long history must get another replay opportunity next time.
  if (!preferReplay) lastReplay.delete(camera);
  const load = async () => {
    if (preferReplay) {
      let response = null;
      try {
        response = await fetch(
          `/event_buffer/${encodeURIComponent(camera)}.gif?recent=1`,
          { cache: "no-store", signal: controller?.signal },
        );
      } catch {
        // Replay is optional. Try saved history within the same deadline;
        // disposal below still prevents late requests after a hold/scene exit.
      }
      if (disposed) return null;
      if (response?.ok) {
        const start = Number(response.headers.get("X-Replay-Start"));
        const end = Number(response.headers.get("X-Replay-End"));
        const frames = Number(response.headers.get("X-Replay-Frames"));
        const fps = Number(response.headers.get("X-Replay-Fps"));
        if (
          [start, end, frames, fps].every(Number.isFinite) &&
          start > 0 &&
          end > start &&
          end - start <= 30 &&
          Date.now() / 1000 - end <= 30 &&
          end <= Date.now() / 1000 + 5 &&
          Number.isInteger(frames) &&
          frames >= 2 &&
          frames <= 30 &&
          fps > 0 &&
          fps <= 30
        ) {
          return {
            response,
            start,
            end,
            fps,
            replay: true,
            duration: Math.min(12, ((end - start) * frames) / (frames - 1)),
          };
        }
      }
    }
    if (disposed) return null;
    const response = await takeTimelapse();
    if (!response?.ok) return null;
    const start = Number(response.headers.get("X-Timelapse-Start"));
    const end = Number(response.headers.get("X-Timelapse-End"));
    const frames = Number(response.headers.get("X-Timelapse-Frames"));
    const duration = Number(response.headers.get("X-Timelapse-Duration"));
    if (
      ![start, end, frames, duration].every(Number.isFinite) ||
      end - start < 600 ||
      end - start > 86400 ||
      Date.now() / 1000 - end > 5400 ||
      end > Date.now() / 1000 + 5 ||
      frames < 6 ||
      frames > 24 ||
      duration <= 0 ||
      duration > 25
    )
      return null;
    if (historyMemory.repeats(camera, start, end)) return null;
    return { response, start, end, duration, replay: false };
  };
  load()
    .then(async (clip) => {
      if (!clip || disposed) {
        dispose();
        return;
      }
      const { response, start, end, duration, replay, fps } = clip;
      const blob = await response.blob();
      if (disposed) return;
      objectUrl = URL.createObjectURL(blob);
      image.onload = () => {
        if (disposed || document.hidden) {
          dispose();
          return;
        }
        window.clearTimeout(timeout);
        if (replay) {
          lastReplay.add(camera);
          title.textContent = `${camera} · RECENT REPLAY`;
          image.alt = `${camera} recorded short replay`;
        } else {
          lastReplay.delete(camera);
          historyMemory.remember(camera, start, end);
        }
        const startedAt = performance.now();
        const tick = () => {
          const elapsed = Math.max(0, (performance.now() - startedAt) / 1000);
          progress.value = Math.min(1, elapsed / duration);
          next.textContent = ` · ${Math.max(0, Math.ceil(duration - elapsed))}s left · Next: latest capture`;
          detail.textContent = replay
            ? `${Math.round(duration)}s preview · from ${captureAge(new Date(start * 1000).toISOString())} · ${fps} fps measured · recorded, not live`
            : historyLabel(start, end);
        };
        tick();
        host.append(node);
        scene.classList.add("has-timelapse");
        onReady(duration);
        ageTimer = window.setInterval(tick, 1000);
        fadeTimer = window.setTimeout(
          () => node.classList.add("is-ending"),
          Math.max(0, duration * 1000 - 350),
        );
        lifetime = window.setTimeout(dispose, duration * 1000);
      };
      image.onerror = dispose;
      image.src = objectUrl;
    })
    .catch(dispose);
  return { dispose };
}

export function historyLabel(start, end) {
  const minutes = Math.round((end - start) / 60);
  const span =
    minutes >= 120 ? `${(minutes / 60).toFixed(1)} HOURS` : `${minutes} MIN`;
  const format = (stamp) =>
    new Date(stamp * 1000).toLocaleString([], {
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
    });
  return `${span} OF HISTORY · ${format(start)} – ${format(end)} · sampled, recorded${end - start < 23 * 3600 ? " · shorter available history" : ""}`;
}
