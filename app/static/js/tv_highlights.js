import { prepareSceneComfort } from "./room_comfort.js?v=20261009-night-clamp";
import { overviewFadeDuration } from "./rotation_overview.js?v=20261015-setup-timeout";

// Reviewed recorded TV joins the rotation sparingly, with explicit source time.
const failedUntil = new Map();
const MEMORY = "glimpser.tv-highlights.seen.v1";
const CLIP = /^tv-\d{13}-\d{1,3}_\d{1,3}$/;

export function chooseHighlight(catalogs, storage, profile, now = Date.now()) {
  if (!["office", "living"].includes(profile)) return null;
  let seen = {};
  try {
    seen = JSON.parse(storage?.getItem(MEMORY) || "{}");
  } catch {
    /* Session can continue. */
  }
  if (!seen || typeof seen !== "object" || Array.isArray(seen)) seen = {};
  for (const [id, until] of failedUntil)
    if (until <= now) failedUntil.delete(id);
  const clips = catalogs.find(
    (model) => model?.dashboard === "local-tv",
  )?.clips;
  return (
    (Array.isArray(clips) ? clips : []).find(
      (clip) =>
        clip &&
        CLIP.test(clip.id) &&
        !(failedUntil.get(clip.id) > now) &&
        clip.video === `/feed-tv/${clip.id}/clip.mp4` &&
        Number.isFinite(clip.duration) &&
        clip.duration >= 20 &&
        clip.duration <= 330 &&
        Number.isFinite(clip.recorded_at) &&
        now / 1000 - clip.recorded_at >= 0 &&
        now / 1000 - clip.recorded_at < 10800 &&
        !(Number(seen[clip.id]) > now - 86400000),
    ) || null
  );
}

export function createHighlight(clip, host, onReady, onFinish, storage) {
  const node = document.createElement("section");
  node.className = "rotation-overview is-tv";
  const tile = document.createElement("div");
  tile.className = "rotation-overview-tile landing-hero-media";
  tile.dataset.heroName = `TV · ${clip.station}`;
  // No still preview is available: use the same safe cap as unknown camera media.
  prepareSceneComfort(tile, null);
  const layer = document.createElement("div");
  layer.className = "kiosk-live-layer";
  const video = document.createElement("video");
  video.className = "landing-hero-video";
  video.muted = true;
  video.autoplay = true;
  video.playsInline = true;
  video.src = clip.video;
  const label = document.createElement("header");
  label.className = "";
  label.textContent = `${clip.station} · RECORDED ${new Date(clip.recorded_at * 1000).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })} · ${clip.title}`;
  const captions = document.createElement("track");
  captions.kind = "captions";
  captions.srclang = "en";
  captions.default = true;
  captions.src = `/feed-tv/${clip.id}/captions.vtt`;
  video.append(captions);
  layer.append(video);
  tile.append(layer);
  node.append(label, tile);
  let finished = false;
  let disposed = false,
    ready = false,
    previous = 0,
    watchedSeconds = 0,
    remembered = false,
    changed = Date.now();
  const started = Date.now();
  let fade;
  const dispose = () => {
    if (disposed) return;
    disposed = true;
    window.removeEventListener("pagehide", dispose);
    clearInterval(watchdog);
    clearTimeout(fade);
    video.onended = null;
    video.onerror = null;
    video.pause();
    video.removeAttribute("src");
    video.load();
    node.remove();
  };
  const finish = () => {
    if (disposed || finished) return;
    finished = true;
    clearInterval(watchdog);
    video.onended = null;
    video.onerror = null;
    if (ready) {
      node.classList.add("is-leaving");
      node.setAttribute("aria-hidden", "true");
      const reduced = window.matchMedia?.(
        "(prefers-reduced-motion: reduce)",
      ).matches;
      const duration = reduced
        ? 600
        : overviewFadeDuration(
            getComputedStyle(host).getPropertyValue("--room-crossfade"),
          );
      fade = setTimeout(dispose, duration + 100);
    } else dispose();
    onFinish([]);
  };
  const unavailable = () => {
    if (disposed || finished) return;
    // Retry another reviewed clip next time instead of repeatedly selecting a
    // broken file. Session-only and bounded; successful clips retain seen history.
    failedUntil.delete(clip.id);
    failedUntil.set(clip.id, Date.now() + 300000);
    while (failedUntil.size > 100)
      failedUntil.delete(failedUntil.keys().next().value);
    finish();
  };
  const watchdog = setInterval(() => {
    if (disposed) return;
    if (video.currentTime > previous && video.videoWidth > 0 && !video.paused) {
      watchedSeconds += Math.min(
        video.currentTime - previous,
        Math.max(0, (Date.now() - changed) / 1000),
        1,
      );
      previous = video.currentTime;
      changed = Date.now();
      if (!ready) {
        ready = true;
        host.append(node);
        layer.classList.add("is-playing");
        // This is recorded video: do not attach the live-player telemetry class.
        onReady();
      }
      if (!remembered && watchedSeconds >= 10) {
        remembered = true;
        try {
          const old = JSON.parse(storage?.getItem(MEMORY) || "{}");
          const rows = Object.entries(old || {})
            .filter(([, at]) => Number(at) > Date.now() - 86400000)
            .slice(-99);
          storage?.setItem(
            MEMORY,
            JSON.stringify(
              Object.fromEntries([...rows, [clip.id, Date.now()]]),
            ),
          );
        } catch {
          /* Playback never depends on storage. */
        }
      }
    }
    if (
      (!ready && Date.now() - started > 12000) ||
      (ready && Date.now() - changed > 5000) ||
      Date.now() - started > (clip.duration + 20) * 1000
    )
      unavailable();
  }, 1000);
  window.addEventListener("pagehide", dispose, { once: true });
  video.onended = finish;
  video.onerror = unavailable;
  try {
    Promise.resolve(video.play()).catch(unavailable);
  } catch {
    unavailable();
  }
  return { cameras: [], dispose };
}
