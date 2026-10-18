import { presentationValue } from "./presentation_config.js";
import { fitCameraMedia } from "./camera_fit.js?v=20261018-bounded";
import { connectGoogleLive } from "./google_live.js?v=20261017-media-lifecycle";
// Include verified door streams even when their source frame rate is low.
export const LIVE_PILOT_CAMERAS = new Set([
  "FrontDoor",
  presentationValue("StoreOneEntryFisheye"),
  "Driveway",
  "Garage",
  "Walkway",
  "Street",
]);
export const GOOGLE_LIVE_CAMERAS = new Set([
  "Front_door_doorbell",
  "Showroom_Entrance",
  "Beach_Google_Front_Door",
  presentationValue("StoreTwo_Google_Showroom"),
]);
for (const camera of GOOGLE_LIVE_CAMERAS) LIVE_PILOT_CAMERAS.add(camera);
// These sources are RTSP in the current office catalog. Keep the list explicit
// so a web page or snapshot with a similar group name is never treated as live.
export const STORE_LIVE_CAMERAS = new Set([
  presentationValue("StoreOneShowroomWide"),
  presentationValue("StoreOneDisplayCase"),
  presentationValue("StoreOne100"),
  presentationValue("StoreOne200"),
  presentationValue("StoreOne300"),
  presentationValue("StoreOne400"),
  presentationValue("StoreOne500"),
  presentationValue("StoreOne1000"),
  presentationValue("StoreOne1500"),
  presentationValue("StoreOne1600"),
  presentationValue("StoreTwo"),
  presentationValue("StoreTwo019"),
  presentationValue("StoreTwo020"),
  presentationValue("StoreTwo021"),
  presentationValue("StoreTwo022"),
  presentationValue("StoreTwo023"),
  presentationValue("StoreTwo024"),
  presentationValue("StoreTwo034"),
  presentationValue("StoreTwo035"),
  presentationValue("StoreTwo036"),
  presentationValue("StoreTwo037"),
  presentationValue("StoreTwo038"),
  presentationValue("StoreTwo039"),
  presentationValue("StoreTwo040"),
]);
export const INTERIOR_LIVE_CAMERAS = new Set(["Safe", "PurpleClonerWide"]);
for (const camera of [...STORE_LIVE_CAMERAS, ...INTERIOR_LIVE_CAMERAS])
  LIVE_PILOT_CAMERAS.add(camera);
export const HOUSE_EXTERIOR_CAMERAS = new Set([
  "Backyard",
  "Garden",
  "BeachDriveway",
  "BeachPathway",
  "BeachSouthJetty",
  "BeachShore",
  "BeachMapleTree",
  "BeachFrontYard",
]);
export const LIVE_CANDIDATE_CAMERAS = new Set([
  ...LIVE_PILOT_CAMERAS,
  ...HOUSE_EXTERIOR_CAMERAS,
]);
export const LIVE_INTERVAL_MS = 60000;
// Share the decoder/data budget between rotating and standalone boards.
export function liveStreamLimit(device = globalThis.navigator) {
  const small = (value) => Number.isFinite(value) && value > 0 && value <= 2;
  return device?.connection?.saveData ||
    small(device?.deviceMemory) ||
    small(device?.hardwareConcurrency)
    ? 1
    : 2;
}

export function liveCameraLabel(camera) {
  return cameraSettings(camera)?.label || camera.replaceAll("_", " ");
}

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
  // More beach airtime must not create more battery-camera wake requests.
  // Scheduled captures and manual viewing remain separate from autoplay.
  if (!cameraSettings(scene?.dataset.heroName)) return false;
  if (
    !["office", "living"].includes(profile) ||
    !cameraSettings(scene?.dataset.heroName)
  )
    return false;
  if (
    (HOUSE_EXTERIOR_CAMERAS.has(scene.dataset.heroName) ||
      STORE_LIVE_CAMERAS.has(scene.dataset.heroName) ||
      INTERIOR_LIVE_CAMERAS.has(scene.dataset.heroName)) &&
    !["rtsp", "hls", "mjpeg", "http_video"].includes(
      scene.dataset.heroMediaKind,
    )
  )
    return false;
  if (scene.dataset.heroMediaKind === "tv" && profile !== "office")
    return false;
  if (scene.dataset.landingFeedUnavailable === "true") return false;
  if (Number(scene.dataset.liveRetryAfter) > Date.now()) return false;
  // Thumbnail age is not broadcast health. The server verifies that the
  // configured YouTube video is currently live before returning any media.
  if (["youtube", "tv"].includes(scene.dataset.heroMediaKind)) return true;
  try {
    const freshness = JSON.parse(
      scene.querySelector("[data-source-freshness]")?.dataset.sourceFreshness ||
        "{}",
    );
    if (
      [
        "capture_overdue",
        "retained",
        "source_unchanged",
        "older",
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

export function mountKioskLive(
  scene,
  {
    offscreen = false,
    onReady = () => {},
    onUnavailable = () => {},
    onStateChange = () => {},
  } = {},
) {
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
  const liveLabel =
    `${cameraLabel} · LIVE` +
    (!google && config.source_fps ? ` · ${config.source_fps} fps source` : "");
  const labelText = document.createTextNode(liveLabel);
  label.append(labelText);
  layer.append(video, label);
  const note = document.createElement("div");
  note.className = "kiosk-live-note";
  note.textContent = "Connecting live · showing saved capture";
  // Keep the decoder attached without exposing a connecting scene. Move the
  // same video into its scene when ready; a second src/play would buffer again.
  const staging = offscreen ? document.createElement("div") : null;
  let revealed = !offscreen;
  if (staging) {
    staging.className = "kiosk-live-staging";
    staging.setAttribute("aria-hidden", "true");
    staging.append(layer, note);
    document.body.append(staging);
  } else host.append(layer, note);
  let disposed = false,
    failed = false,
    ready = false;
  let playbackState = "connecting";
  const setPlaybackState = (state) => {
    if (disposed || failed || state === playbackState) return;
    playbackState = state;
    labelText.nodeValue =
      state === "buffering" ? `${cameraLabel} · Buffering` : liveLabel;
    onStateChange(state);
  };
  let progressSamples = 0;
  let previousProgress = 0,
    lastProgress = Date.now(),
    lastCatchup = -Infinity;
  const started = Date.now();
  const startupTimeoutMs =
    scene.dataset.heroMediaKind === "youtube" ? 35000 : google ? 25000 : 20000;
  const release = () => {
    googleSession?.dispose();
    googleSession = null;
    video.pause();
    video.removeAttribute("src");
    video.load();
    layer.remove();
    if (revealed) scene.classList.remove("has-kiosk-live");
    staging?.remove();
  };
  const fallback = () => {
    if (disposed || failed) return;
    failed = true;
    scene.dataset.liveRetryAfter = String(Date.now() + 300000);
    clearInterval(watchdog);
    release();
    note.textContent = "Saved view · live unavailable";
    if (revealed && !note.isConnected) host.append(note);
    onUnavailable();
  };
  const watchdog = window.setInterval(() => {
    if (disposed || failed) return;
    if (revealed)
      fitCameraMedia(
        video,
        host,
        !["youtube", "tv"].includes(scene.dataset.heroMediaKind),
      );
    const progress = playbackProgress(video);
    // Decoder restarts and media timeline discontinuities can reset counters.
    // Rebase without refreshing the stall deadline: only new frames prove life.
    if (Number.isFinite(progress) && progress < previousProgress)
      previousProgress = progress;
    if (progress > previousProgress && video.videoWidth > 0) {
      previousProgress = progress;
      lastProgress = Date.now();
      setPlaybackState("live");
      if (disposed || failed) return;
      progressSamples += 1;
      if (!ready && (!offscreen || progressSamples >= 2)) {
        ready = true;
        delete scene.dataset.liveRetryAfter;
        if (revealed) scene.classList.add("has-kiosk-live");
        layer.classList.add("is-playing");
        note.remove();
        onReady();
        if (disposed || failed) return;
      }
      // Avoid silently playing far behind the latest available live segment.
      try {
        if (video.seekable.length && Date.now() - lastCatchup >= 10000) {
          const range = video.seekable.length - 1;
          const edge = video.seekable.end(range);
          // Leave decoding headroom and avoid chasing every small buffer wobble.
          if (edge - video.currentTime > 6) {
            video.currentTime = Math.max(
              video.seekable.start(range),
              edge - 1.5,
            );
            lastCatchup = Date.now();
          }
        }
      } catch {
        /* Some live responses expose no seekable range. */
      }
    }
    if (!ready && Date.now() - lastProgress >= 1000) progressSamples = 0;
    if (ready && Date.now() - lastProgress >= 2000)
      setPlaybackState("buffering");
    if (disposed || failed) return;
    if (
      (!ready && Date.now() - started > startupTimeoutMs) ||
      (ready && Date.now() - lastProgress > 5000)
    ) {
      if (revealed && !note.isConnected) host.append(note);
      fallback();
    }
  }, 1000);
  video.addEventListener("error", () => {
    if (revealed && !note.isConnected && !disposed) host.append(note);
    fallback();
  });
  video.addEventListener("ended", fallback);
  if (google) {
    googleSession = connectGoogleLive(video, camera, fallback);
  } else {
    // Main/direct avoids slow substream warm startup on FrontDoor.
    const streamOptions = new URLSearchParams({
      profile: config.profile === "main" ? "main" : "sub",
      quality: config.quality === "auto" ? "auto" : "kiosk",
    }).toString();
    video.src = `/live_video?camera=${encodeURIComponent(camera)}&${streamOptions}`;
    try {
      Promise.resolve(video.play()).catch(fallback);
    } catch {
      // Some older browser implementations throw instead of rejecting play().
      fallback();
    }
  }
  return {
    reveal() {
      if (disposed || failed || !ready) return false;
      if (!revealed) {
        host.append(layer);
        staging?.remove();
        revealed = true;
        scene.classList.add("has-kiosk-live");
      }
      return true;
    },
    get startupRemainingMs() {
      // Include one watchdog tick so rotation cannot race the startup verdict.
      return disposed || failed || ready
        ? 0
        : Math.max(0, started + startupTimeoutMs + 1000 - Date.now());
    },
    get failed() {
      return failed;
    },
    dispose() {
      if (disposed) return;
      disposed = true;
      clearInterval(watchdog);
      release();
      note.remove();
    },
  };
}
