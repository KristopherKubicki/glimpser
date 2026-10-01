import { connectGoogleLive } from "./google_live.js?v=20260926-1";
export const LIVE_INTERVAL_MS = 120000;

function cameraSettings(camera) {
  try {
    const settings = JSON.parse(
      document.getElementById("kiosk-live-settings")?.textContent || "{}",
    );
    if (!Object.hasOwn(settings, camera)) return null;
    const config = settings[camera];
    return config && ["google", "stream"].includes(config.provider)
      ? config
      : null;
  } catch {
    return null;
  }
}

export function livePilotEligible(scene, profile) {
  if (
    !["office", "living"].includes(profile) ||
    !cameraSettings(scene?.dataset.heroName)
  )
    return false;
  if (scene.dataset.landingFeedUnavailable === "true") return false;
  try {
    const freshness = JSON.parse(
      scene.querySelector("[data-source-freshness]")?.dataset.sourceFreshness ||
        "{}",
    );
    if (
      [
        "capture_overdue",
        "retained",
        "clock_ahead",
        "waiting_for_browser",
      ].some((k) => freshness[k])
    )
      return false;
  } catch {
    return false;
  }
  return true;
}

// Media clocks can keep advancing while a WebRTC picture is frozen.
function playbackProgress(video) {
  try {
    const quality = video.getVideoPlaybackQuality?.();
    if (Number.isFinite(quality?.totalVideoFrames)) {
      const dropped = Number.isFinite(quality.droppedVideoFrames)
        ? quality.droppedVideoFrames
        : 0;
      return Math.max(0, quality.totalVideoFrames - dropped);
    }
  } catch {
    // Older browsers can still use the media clock as a best-effort fallback.
  }
  return video.currentTime;
}

export function mountKioskLive(scene, { onReady = () => {} } = {}) {
  const host = scene.querySelector(".landing-hero-media");
  const camera = scene.dataset.heroName;
  const config = cameraSettings(camera);
  if (!config || !host) return { dispose() {} };
  const google = config.provider === "google";
  let googleSession = null;
  const layer = document.createElement("div");
  layer.className = "kiosk-live-layer";
  const video = document.createElement("video");
  video.muted = true;
  video.autoplay = true;
  video.playsInline = true;
  const label = document.createElement("div");
  label.className = "kiosk-live-label";
  const cameraLabel = config.label || camera.replaceAll("_", " ");
  label.textContent = `${cameraLabel} · LIVE`;
  if (!google && config.source_fps) {
    label.textContent += ` · ${config.source_fps} fps source`;
  }
  layer.append(video, label);
  const note = document.createElement("div");
  note.className = "kiosk-live-note";
  note.textContent = "Connecting live · showing saved capture";
  host.append(layer, note);
  let disposed = false,
    failed = false,
    ready = false;
  let previousProgress = 0,
    lastProgress = Date.now();
  const started = Date.now();
  const release = () => {
    googleSession?.dispose();
    googleSession = null;
    video.pause();
    video.removeAttribute("src");
    video.load();
    layer.remove();
    scene.classList.remove("has-kiosk-live");
  };
  const fallback = () => {
    if (disposed || failed) return;
    failed = true;
    clearInterval(watchdog);
    release();
    note.textContent = "SAVED · live unavailable — continuing rotation";
    if (!note.isConnected) host.append(note);
  };
  const watchdog = window.setInterval(() => {
    if (disposed || failed) return;
    const progress = playbackProgress(video);
    if (progress > previousProgress && video.videoWidth > 0) {
      previousProgress = progress;
      lastProgress = Date.now();
      if (!ready) {
        ready = true;
        scene.classList.add("has-kiosk-live");
        layer.classList.add("is-playing");
        note.remove();
        onReady();
      }
      // Avoid silently playing far behind the latest available live segment.
      try {
        if (video.seekable.length) {
          const edge = video.seekable.end(video.seekable.length - 1);
          if (edge - video.currentTime > 4)
            video.currentTime = Math.max(0, edge - 0.5);
        }
      } catch {
        /* Some live responses expose no seekable range. */
      }
    }
    if (
      (!ready && Date.now() - started > (google ? 25000 : 20000)) ||
      (ready && Date.now() - lastProgress > 5000)
    ) {
      if (!note.isConnected) host.append(note);
      fallback();
    }
  }, 1000);
  video.addEventListener("error", () => {
    if (!note.isConnected && !disposed) host.append(note);
    fallback();
  });
  if (google) {
    googleSession = connectGoogleLive(video, camera, fallback);
  } else {
    const streamOptions = new URLSearchParams({
      profile: config.profile === "main" ? "main" : "sub",
      quality: config.quality === "auto" ? "auto" : "kiosk",
    }).toString();
    video.src = `/live_video?camera=${encodeURIComponent(camera)}&${streamOptions}`;
    Promise.resolve(video.play()).catch(fallback);
  }
  return {
    dispose() {
      if (disposed) return;
      disposed = true;
      clearInterval(watchdog);
      release();
      note.remove();
    },
  };
}
