import { mountKioskIndicators } from "./kiosk_indicators.js?v=20260927-1";
import { canHandoffToDoor } from "./priority_handoff.js?v=20260930-private-rules";
import { simplifyDashboardHud } from "./dashboard_hud.js?v=20260926-1";
import { mountKioskHeartbeat } from "./kiosk_heartbeat.js?v=20260926-1";
import {
  livePilotEligible,
  mountKioskLive,
  LIVE_INTERVAL_MS,
} from "./kiosk_live.js?v=20260930-private-settings";
import {
  mountTimelapse,
  preloadTimelapse,
  timelapseIsDue,
  preferCurrentView,
  TIMELAPSE_INTERVAL_MS,
  TIMELAPSE_PRELOAD_LEAD_MS,
} from "./timelapse_preview.js?v=20260929-history-fallback";
import { createKioskHold } from "./kiosk_hold.js";
import {
  chooseOverview,
  createOverview,
  fetchOverviewCatalogs,
} from "./rotation_overview.js";
import { createPriorityAlert } from "./priority_alert.js?v=20260926-3";
import { captureImageUrl, captureAge } from "./capture_age.js";
import { formatExactTime, timeAgo } from "./time_utils.js";

if (!document.querySelector("link[data-priority-alert-style]")) {
  const style = document.createElement("link");
  style.rel = "stylesheet";
  style.href = "/static/css/priority_alert.css?v=20260922-7";
  style.dataset.priorityAlertStyle = "";
  document.head.append(style);
}

if (!document.querySelector("link[data-kiosk-live-style]")) {
  const style = document.createElement("link");
  style.rel = "stylesheet";
  style.href = "/static/css/kiosk_live.css?v=20260926-2";
  style.dataset.kioskLiveStyle = "";
  document.head.append(style);
}

const DEFAULT_LANDING_CHROME_FADE_MS = 2400;
const DEFAULT_LANDING_EVENT_POLL_MS = 15000;
const DEFAULT_LANDING_IMAGE_REFRESH_MS = 180000;
const DEFAULT_LANDING_ROTATION_MS = 60000;
const HERO_IMAGE_DARK_MEAN_MAX = 26;
// Hubitat loading shells use blue-gray (~40 luma), not black.
const HERO_IMAGE_BLANK_SHELL_MEAN_MAX = 48;
const HERO_IMAGE_LOW_VARIANCE_MAX = 18;
const HERO_IMAGE_BRIGHT_RATIO_MIN = 0.02;
const HERO_IMAGE_TOP_DARK_MEAN_MAX = 16;
const HERO_IMAGE_TOP_BRIGHT_RATIO_MAX = 0.0025;
const HERO_VIDEO_MAX_PROBES = 6;
const HERO_VIDEO_PROBE_INTERVAL_MS = 320;
const HERO_VIDEO_DARK_MEAN_MAX = 18;
const HERO_VIDEO_LOW_VARIANCE_MAX = 14;
const HERO_VIDEO_BRIGHT_RATIO_MIN = 0.01;
const HERO_SCENE_SUPPRESSION_MULTIPLIER = 3;
const HERO_SCENE_SUPPRESSION_MIN_MS = 90000;
const HERO_VISUAL_SAMPLE_WIDTH = 48;
const LANDING_CONTAIN_MEDIA_RATIO_MAX = 0.92;
const LANDING_WIDE_MEDIA_RATIO_MIN = 2.4;
const LANDING_PREVIEW_QUEUE_LENGTH = 3;
const LANDING_SCENE_EXIT_MS = 950;
const LANDING_TIME_REFRESH_MS = 60000;
const LANDING_VIEWPORT_BEACON_DELAY_MS = 800;

function roundedRect(element) {
  if (!element) {
    return null;
  }
  const rect = element.getBoundingClientRect();
  return {
    bottom: Math.round(rect.bottom),
    height: Math.round(rect.height),
    left: Math.round(rect.left),
    right: Math.round(rect.right),
    top: Math.round(rect.top),
    width: Math.round(rect.width),
  };
}

export function buildLandingViewportPayload(shell, reason = "load") {
  const stage = shell?.querySelector(".landing-stage-shell");
  const stageRect = roundedRect(stage);
  const shellRect = roundedRect(shell);
  const visualViewportHeight = window.visualViewport?.height;
  const viewportHeight =
    Number.isFinite(visualViewportHeight) && visualViewportHeight > 0
      ? visualViewportHeight
      : window.innerHeight;
  return {
    reason,
    mode: stage?.dataset.landingMode || "",
    profile: stage?.dataset.landingProfile || "",
    viewport: {
      documentClientHeight: Math.round(
        document.documentElement?.clientHeight || 0,
      ),
      fullscreen: Boolean(document.fullscreenElement),
      devicePixelRatio: window.devicePixelRatio || 1,
      innerHeight: Math.round(window.innerHeight || 0),
      innerWidth: Math.round(window.innerWidth || 0),
      outerToAvailable: Math.round(
        (window.screen?.availHeight || 0) - (window.outerHeight || 0),
      ),
      outerHeight: Math.round(window.outerHeight || 0),
      screenAvailHeight: Math.round(window.screen?.availHeight || 0),
      screenHeight: Math.round(window.screen?.height || 0),
      visualViewportHeight: Math.round(viewportHeight || 0),
    },
    gaps: {
      innerToAvailable: Math.round(
        (window.screen?.availHeight || 0) - window.innerHeight,
      ),
      innerToScreen: Math.round(
        (window.screen?.height || 0) - window.innerHeight,
      ),
      stageBottomToViewport: stageRect
        ? Math.round(viewportHeight - stageRect.bottom)
        : null,
    },
    shell: shellRect,
    stage: stageRect,
  };
}

function sendLandingViewportBeacon(shell, reason) {
  if (window.__GLIMPSER_DISABLE_BEACONS) {
    return;
  }
  try {
    window
      .fetch("/client_beacon", {
        body: JSON.stringify({
          data: buildLandingViewportPayload(shell, reason),
          event: "landing_viewport",
          path: window.location?.pathname || "",
        }),
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        keepalive: true,
        method: "POST",
      })
      .catch(() => {});
  } catch {
    // Kiosk diagnostics should never affect rotation.
  }
}

function initLandingViewportBeacon(shell) {
  let beaconTimer = null;
  const clearBeaconTimer = () => {
    if (beaconTimer) {
      window.clearTimeout(beaconTimer);
      beaconTimer = null;
    }
  };
  const scheduleBeacon = (reason) => {
    clearBeaconTimer();
    beaconTimer = window.setTimeout(() => {
      beaconTimer = null;
      sendLandingViewportBeacon(shell, reason);
    }, LANDING_VIEWPORT_BEACON_DELAY_MS);
  };
  const handleResize = () => scheduleBeacon("resize");
  const handleFullscreen = () => scheduleBeacon("fullscreenchange");

  scheduleBeacon("load");
  window.addEventListener("resize", handleResize);
  document.addEventListener("fullscreenchange", handleFullscreen);

  return () => {
    clearBeaconTimer();
    window.removeEventListener("resize", handleResize);
    document.removeEventListener("fullscreenchange", handleFullscreen);
  };
}

export function syncLandingViewportHeight() {
  const visualHeight = window.visualViewport?.height;
  const viewportHeight =
    Number.isFinite(visualHeight) && visualHeight > 0
      ? visualHeight
      : window.innerHeight;
  if (!Number.isFinite(viewportHeight) || viewportHeight <= 0) {
    return;
  }
  document.documentElement.style.setProperty(
    "--eyebat-landing-viewport-height",
    `${Math.round(viewportHeight)}px`,
  );
}

function initLandingViewportHeightSync() {
  const scheduleSync = () => {
    if (typeof window.requestAnimationFrame === "function") {
      window.requestAnimationFrame(syncLandingViewportHeight);
      return;
    }
    window.setTimeout(syncLandingViewportHeight, 0);
  };
  const visualViewport = window.visualViewport;
  syncLandingViewportHeight();
  window.addEventListener("resize", scheduleSync);
  window.addEventListener("orientationchange", scheduleSync);
  document.addEventListener("fullscreenchange", scheduleSync);
  visualViewport?.addEventListener?.("resize", scheduleSync);
  visualViewport?.addEventListener?.("scroll", scheduleSync);

  return () => {
    window.removeEventListener("resize", scheduleSync);
    window.removeEventListener("orientationchange", scheduleSync);
    document.removeEventListener("fullscreenchange", scheduleSync);
    visualViewport?.removeEventListener?.("resize", scheduleSync);
    visualViewport?.removeEventListener?.("scroll", scheduleSync);
  };
}

function updateTimeLabels(root) {
  root.querySelectorAll("[data-capture-age]").forEach((element) => {
    element.textContent = captureAge(element.dataset.captureAge);
    element.title = element.dataset.captureAge
      ? `${element.dataset.captureAge} UTC`
      : "Awaiting capture";
  });
  root.querySelectorAll("[data-human-time]").forEach((element) => {
    const timestamp = element.dataset.humanTime || "";
    if (!timestamp) {
      element.textContent = "Awaiting capture";
      element.title = "Awaiting capture";
      return;
    }
    element.textContent = timeAgo(timestamp);
    element.title = formatExactTime(timestamp);
  });
}

function parsePositiveInt(value, fallback) {
  const parsed = Number.parseInt(value || "", 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

function parseNonNegativeInt(value, fallback) {
  const parsed = Number.parseInt(value || "", 10);
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : fallback;
}

function parseBooleanFlag(value) {
  return String(value || "").toLowerCase() === "true";
}

// Publish a new capture age only after its replacement image loads. Metadata
// polls can succeed while the image request fails; the old frame must keep its age.
function expectCaptureForImage(image) {
  if (!image.matches(".landing-hero-media img")) return;
  const scene = image.closest(".landing-scene");
  if (!scene) return;
  image.dataset.expectedCaptureTime =
    scene.dataset.heroLastScreenshotTime || "";
  image.dataset.expectedSourceFreshness =
    scene.dataset.heroSourceFreshness ||
    scene.querySelector("[data-source-freshness]")?.dataset.sourceFreshness ||
    "{}";
}

export function updateSceneCaptureMetadata(scene, timestamp, freshness) {
  const changed = scene.dataset.heroLastScreenshotTime !== timestamp;
  scene.dataset.heroLastScreenshotTime = timestamp;
  if (freshness) {
    scene.dataset.heroSourceFreshness = JSON.stringify(freshness);
    // A repeated metadata poll is not proof that the new image loaded.
    const displayed =
      scene.querySelector("[data-capture-age]")?.dataset.captureAge;
    if (!changed && displayed === timestamp)
      scene.querySelectorAll("[data-source-freshness]").forEach((node) => {
        node.dataset.sourceFreshness = JSON.stringify(freshness);
      });
  }
  return changed;
}

export function commitLoadedCapture(image) {
  if (!image.matches(".landing-hero-media img") || !image.naturalWidth) return;
  const scene = image.closest(".landing-scene");
  if (!scene || !image.dataset.expectedCaptureTime) return;
  scene.querySelectorAll("[data-capture-age]").forEach((node) => {
    node.dataset.captureAge = image.dataset.expectedCaptureTime;
  });
  scene.querySelectorAll("[data-source-freshness]").forEach((node) => {
    node.dataset.sourceFreshness =
      image.dataset.expectedSourceFreshness || "{}";
  });
  updateTimeLabels(scene);
}

function buildRefreshUrl(baseUrl, image) {
  baseUrl = captureImageUrl(baseUrl, image?.dataset.expectedCaptureTime);
  if (!baseUrl) {
    return "";
  }
  const separator = baseUrl.includes("?") ? "&" : "?";
  return `${baseUrl}${separator}_ts=${Date.now()}`;
}

function setRefreshableImageSource(image, baseUrl) {
  if (!image) return;
  if (!baseUrl) {
    image.removeAttribute("src");
    delete image.dataset.refreshSrc;
    image
      .closest(".landing-hero-media, .landing-pip-card, .landing-deck-card")
      ?.classList.remove("is-contained");
    return;
  }
  image.dataset.refreshSrc = baseUrl;
  expectCaptureForImage(image);
  image.src = buildRefreshUrl(baseUrl, image);
}

function readSceneMedia(scene) {
  if (!scene) {
    return null;
  }

  if (scene._landingMedia) {
    return scene._landingMedia;
  }

  const hero = {
    imageUrl: scene.dataset.heroImageUrl || "",
    lastScreenshotTime: scene.dataset.heroLastScreenshotTime || "",
    liveUrl: scene.dataset.heroLiveUrl || "",
    name: scene.dataset.heroName || "",
    videoUrl: scene.dataset.heroVideoUrl || "",
  };
  const pip = scene.dataset.pipImageUrl
    ? {
        imageUrl: scene.dataset.pipImageUrl || "",
        liveUrl: scene.dataset.pipLiveUrl || "",
        name: scene.dataset.pipName || "",
        videoUrl: scene.dataset.pipVideoUrl || "",
      }
    : null;

  scene._landingMedia = {
    hero,
    pip,
    sceneId: scene.dataset.sceneId || "",
  };
  return scene._landingMedia;
}

function setPreviewVideo(video, media) {
  if (!video) return;

  if (!media?.videoUrl) {
    video.pause();
    setVideoReadyState(video, false);
    clearSceneVideoProbe(video);
    video.removeAttribute("src");
    video.removeAttribute("poster");
    delete video.dataset.videoSrc;
    video.load();
    return;
  }

  video.dataset.videoSrc = media.videoUrl;
  if (media.imageUrl) {
    video.setAttribute("poster", media.imageUrl);
  } else {
    video.removeAttribute("poster");
  }
  setVideoReadyState(video, false);
}

function applyAtBatSlot(scene, sourceScene) {
  const card = scene?.querySelector(".landing-pip-card");
  if (!card) return;

  const image = card.querySelector("img");
  const video = card.querySelector(".landing-pip-video");
  const step = card.querySelector(".landing-pip-age");
  const title = card.querySelector(".landing-pip-title");

  if (!sourceScene) {
    card.hidden = true;
    card.removeAttribute("href");
    setRefreshableImageSource(image, "");
    setPreviewVideo(video, null);
    if (step) step.textContent = "At Bat";
    if (title) title.textContent = "";
    return;
  }

  const sceneMedia = readSceneMedia(sourceScene);
  const previewMedia = sceneMedia?.pip || sceneMedia?.hero;
  if (!previewMedia) {
    card.hidden = true;
    return;
  }

  card.hidden = false;
  card.href = sceneMedia.hero.liveUrl || previewMedia.liveUrl || "#";
  if (step) step.textContent = "At Bat";
  if (title)
    title.textContent = sceneMedia.hero.name || previewMedia.name || "";
  if (image) {
    image.alt = `${sceneMedia.hero.name || previewMedia.name || "Upcoming"} at bat preview`;
    setRefreshableImageSource(image, previewMedia.imageUrl);
  }
  setPreviewVideo(video, previewMedia);
}

function applyDeckSlot(card, sourceScene, label) {
  if (!card) return;

  const image = card.querySelector("img");
  const step = card.querySelector(".landing-deck-step");
  const title = card.querySelector(".landing-deck-title");

  if (!sourceScene) {
    card.hidden = true;
    card.removeAttribute("href");
    if (step) step.textContent = label;
    if (title) title.textContent = "";
    setRefreshableImageSource(image, "");
    return;
  }

  const sceneMedia = readSceneMedia(sourceScene);
  if (!sceneMedia?.hero) {
    card.hidden = true;
    return;
  }

  card.hidden = false;
  card.href = sceneMedia.hero.liveUrl || "#";
  if (step) step.textContent = label;
  if (title) title.textContent = sceneMedia.hero.name || "";
  if (image) {
    image.alt = `${sceneMedia.hero.name || "Upcoming"} ${label.toLowerCase()} preview`;
    setRefreshableImageSource(image, sceneMedia.hero.imageUrl);
  }
}

function syncSceneQueueSlots(scene, scenes, queueIndices) {
  if (!scene) return;

  applyAtBatSlot(scene, scenes[queueIndices[0]]);

  const deckCards = Array.from(
    scene.querySelectorAll(".landing-deck-card[data-landing-queue-slot]"),
  );
  const labels = ["On Deck", "In Queue"];
  deckCards.forEach((card, slotIndex) => {
    applyDeckSlot(card, scenes[queueIndices[slotIndex + 1]], labels[slotIndex]);
  });
}

function findNextEligibleSceneIndex(
  scenes,
  startIndex,
  excludedIndices = new Set(),
  isSceneSuppressed = () => false,
) {
  let fallbackIndex = -1;

  for (let offset = 1; offset < scenes.length; offset += 1) {
    const candidateIndex = (startIndex + offset) % scenes.length;
    if (excludedIndices.has(candidateIndex)) {
      continue;
    }
    if (fallbackIndex < 0) {
      fallbackIndex = candidateIndex;
    }
    if (!isSceneSuppressed(scenes[candidateIndex])) {
      return candidateIndex;
    }
  }

  return fallbackIndex;
}

export function buildLandingQueue(
  scenes,
  currentIndex,
  isSceneSuppressed = () => false,
  queueLength = LANDING_PREVIEW_QUEUE_LENGTH,
) {
  if (!Array.isArray(scenes) || scenes.length <= 1) {
    return [];
  }

  // Promote upcoming assets in a stable order so the right rail behaves like a
  // broadcast carousel instead of a static "next few groups" preview list.
  const maxQueueLength = Math.min(queueLength, scenes.length - 1);
  const queue = [];
  const usedIndices = new Set([currentIndex]);
  let cursor = currentIndex;

  while (queue.length < maxQueueLength) {
    const nextIndex = findNextEligibleSceneIndex(
      scenes,
      cursor,
      usedIndices,
      isSceneSuppressed,
    );
    if (nextIndex < 0) {
      break;
    }
    queue.push(nextIndex);
    usedIndices.add(nextIndex);
    cursor = nextIndex;
  }

  return queue;
}

export function shouldContainMediaFrame(width, height) {
  if (
    !Number.isFinite(width) ||
    !Number.isFinite(height) ||
    width <= 0 ||
    height <= 0
  ) {
    return false;
  }

  const ratio = width / height;
  // Wide graphs need their axes preserved just as portrait cameras need their height.
  return (
    ratio < LANDING_CONTAIN_MEDIA_RATIO_MAX ||
    ratio > LANDING_WIDE_MEDIA_RATIO_MIN
  );
}

function setMediaFitClass(container, width, height) {
  if (!container) return;
  container.classList.toggle(
    "is-contained",
    shouldContainMediaFrame(width, height),
  );
}

function syncImageFit(image) {
  if (
    !image ||
    !image.complete ||
    !image.naturalWidth ||
    !image.naturalHeight
  ) {
    return;
  }

  const container = image.closest(
    ".landing-hero-media, .landing-pip-card, .landing-deck-card",
  );
  setMediaFitClass(container, image.naturalWidth, image.naturalHeight);
}

function bindImageFit(image) {
  if (!image || image.dataset.landingFitBound === "true") {
    return;
  }

  image.dataset.landingFitBound = "true";
  image.addEventListener("load", () => {
    syncImageFit(image);
    commitLoadedCapture(image);
  });
  image.addEventListener("error", () => {
    const container = image.closest(
      ".landing-hero-media, .landing-pip-card, .landing-deck-card",
    );
    container?.classList.remove("is-contained");
  });
  syncImageFit(image);
}

function refreshVisibleImages(scene) {
  if (!scene) return;

  scene.querySelectorAll("img[data-refresh-src]").forEach((image) => {
    const baseUrl = image.dataset.refreshSrc;
    if (!baseUrl) return;

    refreshLandingImage(image, baseUrl);
  });
}

export function refreshLandingImage(image, baseUrl) {
  if (image._landingRefreshPending) return;
  const scene = image.matches(".landing-hero-media img")
    ? image.closest(".landing-scene")
    : null;
  const capture =
    scene?.dataset.heroLastScreenshotTime || image.dataset.expectedCaptureTime;
  const freshness =
    scene?.dataset.heroSourceFreshness ||
    scene?.querySelector("[data-source-freshness]")?.dataset.sourceFreshness ||
    image.dataset.expectedSourceFreshness;
  const pending = new Image();
  image._landingRefreshPending = pending;
  let finished = false;
  const finish = (ok) => {
    if (finished) return;
    finished = true;
    window.clearTimeout(timer);
    image._landingRefreshPending = null;
    pending.onload = null;
    pending.onerror = null;
    if (!image.isConnected) return;
    if (ok) {
      if (capture) image.dataset.expectedCaptureTime = capture;
      if (freshness) image.dataset.expectedSourceFreshness = freshness;
      image.src = pending.src;
    } else image.dispatchEvent(new Event("landing-image-failed"));
  };
  const timer = window.setTimeout(() => finish(false), 8000);
  image._landingCancelRefresh = () => {
    finished = true;
    window.clearTimeout(timer);
    pending.onload = null;
    pending.onerror = null;
    pending.removeAttribute("src");
    image._landingRefreshPending = null;
  };
  pending.onload = () => finish(Boolean(pending.naturalWidth));
  pending.onerror = () => finish(false);
  pending.src = buildRefreshUrl(baseUrl, {
    dataset: { expectedCaptureTime: capture },
  });
}

function sampleVisualStats(
  target,
  width,
  height,
  sampleWidth = HERO_VISUAL_SAMPLE_WIDTH,
) {
  if (!target || !width || !height) {
    return null;
  }

  const canvas = target._landingProbeCanvas || document.createElement("canvas");
  const context =
    target._landingProbeContext ||
    canvas.getContext?.("2d", { willReadFrequently: true });
  if (!context) {
    return null;
  }

  const sampleHeight = Math.max(27, Math.round((sampleWidth * height) / width));
  const topBandHeight = Math.max(1, Math.floor(sampleHeight * 0.58));
  canvas.width = sampleWidth;
  canvas.height = sampleHeight;
  target._landingProbeCanvas = canvas;
  target._landingProbeContext = context;

  try {
    context.drawImage(target, 0, 0, sampleWidth, sampleHeight);
    const frame = context.getImageData(0, 0, sampleWidth, sampleHeight).data;
    let lumaSum = 0;
    let lumaSquaredSum = 0;
    let brightPixels = 0;
    let topLumaSum = 0;
    let topBrightPixels = 0;

    for (let i = 0; i < frame.length; i += 4) {
      const pixelIndex = i / 4;
      const row = Math.floor(pixelIndex / sampleWidth);
      const luma =
        0.2126 * frame[i] + 0.7152 * frame[i + 1] + 0.0722 * frame[i + 2];

      lumaSum += luma;
      lumaSquaredSum += luma * luma;
      if (luma >= 72) {
        brightPixels += 1;
      }

      if (row < topBandHeight) {
        topLumaSum += luma;
        if (luma >= 72) {
          topBrightPixels += 1;
        }
      }
    }

    const pixelCount = frame.length / 4;
    const mean = lumaSum / pixelCount;
    const variance = Math.max(0, lumaSquaredSum / pixelCount - mean * mean);
    const stddev = Math.sqrt(variance);
    const brightRatio = brightPixels / pixelCount;
    const topPixelCount = sampleWidth * topBandHeight;

    return {
      brightRatio,
      mean,
      stddev,
      topBrightRatio: topBrightPixels / topPixelCount,
      topMean: topLumaSum / topPixelCount,
    };
  } catch {
    return null;
  }
}

function clearSceneVideoProbe(video) {
  if (!video) return;
  if (video._landingProbeTimer) {
    window.clearInterval(video._landingProbeTimer);
    video._landingProbeTimer = null;
  }
  video._landingProbeAttempts = 0;
  video.onloadeddata = null;
  video.oncanplay = null;
  video.ontimeupdate = null;
}

function setVideoReadyState(video, isReady) {
  if (!video) return;

  video.classList.toggle("is-ready", isReady);
  video
    .closest(".landing-hero-media, .landing-pip-card")
    ?.classList.toggle("has-ready-video", isReady);
}

export function hasUsableImageFrame(image) {
  if (
    !image ||
    !image.complete ||
    !image.naturalWidth ||
    !image.naturalHeight
  ) {
    return null;
  }

  const stats = sampleVisualStats(
    image,
    image.naturalWidth,
    image.naturalHeight,
  );
  if (!stats) {
    return true;
  }

  const blank = (sample) =>
    (sample.mean < HERO_IMAGE_BLANK_SHELL_MEAN_MAX &&
      sample.stddev < HERO_IMAGE_LOW_VARIANCE_MAX &&
      sample.brightRatio < HERO_IMAGE_BRIGHT_RATIO_MIN) ||
    (sample.topMean < HERO_IMAGE_TOP_DARK_MEAN_MAX &&
      sample.topBrightRatio < HERO_IMAGE_TOP_BRIGHT_RATIO_MAX &&
      sample.mean < HERO_IMAGE_DARK_MEAN_MAX * 1.8);
  if (!blank(stats)) return true;
  // Thin chart lines disappear in the tiny camera probe. Confirm a suspected
  // blank at higher resolution before hiding a valid dark dashboard.
  const detailed = sampleVisualStats(
    image,
    image.naturalWidth,
    image.naturalHeight,
    192,
  );
  return !detailed || !blank(detailed);
}

// A short clip must not turn a calm scene into a rapid slideshow.
export function timelapseSceneDwellMs(sceneMs, durationSeconds) {
  return Math.max(sceneMs, durationSeconds * 1000 + 1000);
}

export function canInterruptScene(
  priority,
  shownAt,
  dwellMs,
  now = Date.now(),
) {
  return Boolean(priority) || now - shownAt >= dwellMs;
}

function hasUsableVideoFrame(video) {
  if (
    !video ||
    video.readyState < 2 ||
    !video.videoWidth ||
    !video.videoHeight
  ) {
    return false;
  }

  const stats = sampleVisualStats(video, video.videoWidth, video.videoHeight);
  if (!stats) {
    return true;
  }

  return !(
    stats.mean < HERO_VIDEO_DARK_MEAN_MAX &&
    stats.stddev < HERO_VIDEO_LOW_VARIANCE_MAX &&
    stats.brightRatio < HERO_VIDEO_BRIGHT_RATIO_MIN
  );
}

function armSceneVideoProbe(video) {
  if (!video) return;

  clearSceneVideoProbe(video);
  video._landingProbeAttempts = 0;

  const runProbe = () => {
    if (!video.getAttribute("src")) {
      clearSceneVideoProbe(video);
      return;
    }

    if (video.readyState < 2 || !video.videoWidth || !video.videoHeight) {
      return;
    }

    const container = video.closest(".landing-hero-media, .landing-pip-card");
    setMediaFitClass(container, video.videoWidth, video.videoHeight);

    video._landingProbeAttempts += 1;
    if (hasUsableVideoFrame(video)) {
      setVideoReadyState(video, true);
      clearSceneVideoProbe(video);
      return;
    }

    if (video._landingProbeAttempts >= HERO_VIDEO_MAX_PROBES) {
      video.pause();
      setVideoReadyState(video, false);
      video.removeAttribute("src");
      video.load();
      clearSceneVideoProbe(video);
    }
  };

  video.onloadeddata = runProbe;
  video.oncanplay = runProbe;
  video.ontimeupdate = runProbe;
  video._landingProbeTimer = window.setInterval(
    runProbe,
    HERO_VIDEO_PROBE_INTERVAL_MS,
  );
}

function syncSceneMediaVideo(scene, selector, isVisible) {
  if (!scene) return;

  const video = scene.querySelector(selector);
  if (!video) return;

  const videoSrc = video.dataset.videoSrc;
  if (!videoSrc) return;

  if (!isVisible || document.hidden) {
    video.pause();
    setVideoReadyState(video, false);
    clearSceneVideoProbe(video);
    video.removeAttribute("src");
    video.load();
    return;
  }

  if (video.getAttribute("src") !== videoSrc) {
    setVideoReadyState(video, false);
    video.setAttribute("src", videoSrc);
    video.load();
    armSceneVideoProbe(video);
  }

  const playbackRate = parseFloat(video.dataset.playbackRate || "0.18");
  if (Number.isFinite(playbackRate) && playbackRate > 0) {
    video.playbackRate = playbackRate;
  }

  const playPromise = video.play();
  if (playPromise && typeof playPromise.catch === "function") {
    playPromise.catch(() => {
      // Autoplay can be denied in some kiosk shells. Keep the still visible.
      setVideoReadyState(video, false);
    });
  }
}

function syncSceneVideo(scene, isVisible) {
  syncSceneMediaVideo(scene, ".landing-hero-video", isVisible);
  syncSceneMediaVideo(scene, ".landing-pip-video", isVisible);
}

function setChromeVisibility(shell, isVisible) {
  shell.classList.toggle("is-chrome-visible", isVisible);
}

function initChromeAutoHide(shell, hideAfterMs) {
  if (!shell || hideAfterMs <= 0) return () => {};

  let chromeTimer = null;

  const clearChromeTimer = () => {
    if (chromeTimer) {
      window.clearTimeout(chromeTimer);
      chromeTimer = null;
    }
  };

  const scheduleHide = () => {
    clearChromeTimer();
    chromeTimer = window.setTimeout(() => {
      const focused = document.activeElement;
      if (
        shell.contains(focused) &&
        focused?.matches(
          ":focus-visible, input, select, textarea, [contenteditable='true']",
        )
      ) {
        scheduleHide();
        return;
      }
      setChromeVisibility(shell, false);
    }, hideAfterMs);
  };

  const revealChrome = () => {
    setChromeVisibility(shell, true);
    scheduleHide();
  };

  setChromeVisibility(shell, true);
  scheduleHide();

  const eventTargets = [
    [window, "pointermove"],
    [window, "pointerdown"],
    [window, "keydown"],
    [document, "focusin"],
    [window, "touchstart"],
  ];
  for (const [target, eventName] of eventTargets) {
    target.addEventListener(eventName, revealChrome, { passive: true });
  }

  return () => {
    clearChromeTimer();
    for (const [target, eventName] of eventTargets) {
      target.removeEventListener(eventName, revealChrome, { passive: true });
    }
  };
}

export function syncSceneImages(scene, active) {
  scene.querySelectorAll("img[data-refresh-src]").forEach((image) => {
    if (active) {
      if (!image.getAttribute("src")) {
        expectCaptureForImage(image);
        image.src = buildRefreshUrl(image.dataset.refreshSrc, image);
      }
    } else {
      image._landingCancelRefresh?.();
      image.removeAttribute("src");
    }
  });
  scene.querySelectorAll("video[poster]").forEach((video) => {
    if (!active) video.removeAttribute("poster");
  });
}

export function showLandingScene(scenes, index, previousIndex = -1) {
  scenes.forEach((scene, sceneIndex) => {
    const isVisible = sceneIndex === index;
    const isExiting = sceneIndex === previousIndex && previousIndex !== index;
    scene.style.display = isVisible || isExiting ? "" : "none";
    scene.classList.toggle("is-visible", isVisible);
    scene.classList.toggle("is-exiting", isExiting);
    scene.setAttribute("aria-hidden", isVisible ? "false" : "true");
    syncSceneImages(scene, isVisible || isExiting);
    syncSceneVideo(
      scene,
      isVisible && scene.dataset.landingPriorityActive !== "true",
    );
  });
}

// Save camera names rather than positions: health changes can reorder the loop.
export function restoreOfficeRotation(scenes, profile) {
  if (!["office", "living"].includes(profile)) return -1;
  try {
    const nextCamera = window.localStorage.getItem(
      `glimpser.${profile}.next-camera.v1`,
    );
    return scenes.findIndex((scene) => scene.dataset.heroName === nextCamera);
  } catch {
    return -1;
  }
}

export function rememberOfficeRotation(scene, profile) {
  if (!["office", "living"].includes(profile) || !scene?.dataset.heroName)
    return;
  try {
    window.localStorage.setItem(
      `glimpser.${profile}.next-camera.v1`,
      scene.dataset.heroName,
    );
  } catch {
    // Storage restrictions must never stop the display from rotating.
  }
}

export function initLanding() {
  const setup = () => {
    const shell = document.querySelector("[data-landing-screen]");
    if (!shell) return;

    const cleanupLandingViewportHeight = initLandingViewportHeightSync();
    const cleanupLandingViewportBeacon = initLandingViewportBeacon(shell);
    const stageShell = shell.querySelector(".landing-stage-shell") || shell;
    // Refresh membership even from an empty pool, while preserving room progress.
    const poolRefreshTimer = ["living", "office"].includes(
      stageShell.dataset.landingProfile,
    )
      ? window.setInterval(
          () => {
            if (
              !document.hidden &&
              !stageShell.classList.contains("has-priority-event") &&
              stageShell.dataset.kioskOffline !== "true"
            )
              window.location.reload();
          },
          15 * 60 * 1000,
        )
      : null;
    window.addEventListener(
      "pagehide",
      () => window.clearInterval(poolRefreshTimer),
      { once: true },
    );
    const scenes = Array.from(shell.querySelectorAll(".landing-scene"));
    if (!scenes.length) {
      window.addEventListener(
        "pagehide",
        () => {
          cleanupLandingViewportHeight();
          cleanupLandingViewportBeacon();
        },
        { once: true },
      );
      return;
    }

    const chromeFadeMs = parseNonNegativeInt(
      stageShell.dataset.landingChromeFadeMs,
      DEFAULT_LANDING_CHROME_FADE_MS,
    );
    const eventsEnabled = parseBooleanFlag(
      stageShell.dataset.landingEventsEnabled,
    );
    const eventPollMs = parseNonNegativeInt(
      stageShell.dataset.landingEventsPollMs,
      DEFAULT_LANDING_EVENT_POLL_MS,
    );
    const eventsUrl = stageShell.dataset.landingEventsUrl || "";
    const rotationMs = parsePositiveInt(
      stageShell.dataset.landingRotationMs,
      DEFAULT_LANDING_ROTATION_MS,
    );
    const imageRefreshMs = parseNonNegativeInt(
      stageShell.dataset.landingRefreshMs,
      DEFAULT_LANDING_IMAGE_REFRESH_MS,
    );
    stageShell.style.setProperty("--landing-rotation-ms", `${rotationMs}ms`);

    let currentIndex = Math.max(
      0,
      scenes.findIndex((scene) => scene.classList.contains("is-visible")),
    );
    let sceneShownAt = Date.now();
    const rotationProfile = stageShell.dataset.landingProfile;
    const continuity = createKioskHold(stageShell, rotationProfile);
    let metadataHealthy = !eventsEnabled;
    mountKioskHeartbeat(rotationProfile);
    mountKioskIndicators(rotationProfile);
    if (["office", "living"].includes(rotationProfile)) {
      simplifyDashboardHud();
      if (!document.querySelector("link[data-dashboard-hud-style]")) {
        const style = document.createElement("link");
        style.rel = "stylesheet";
        style.href = "/static/css/dashboard_hud.css?v=20260926-1";
        style.dataset.dashboardHudStyle = "";
        document.head.append(style);
      }
    }
    let livePilot = null;
    let lastLiveAt = null;
    let timelapse = null;
    let lastTimelapseAt = null;
    let lastHistoryAttemptAt = null;
    let timelapseDue = false;
    const stopTimelapse = () => {
      livePilot?.dispose();
      livePilot = null;
      timelapse?.dispose();
      timelapse = null;
      timelapseDue = false;
    };
    let disposed = false;
    const resumedIndex = restoreOfficeRotation(scenes, rotationProfile);
    if (resumedIndex >= 0) currentIndex = resumedIndex;
    let previousIndex = -1;
    let exitTimer = null;
    let fallbackTimer = null;
    let rotationTimer = null;
    let manualHoldTimer = null;
    let eventPollTimer = null;
    let eventPollInFlight = false;
    let timeTimer = null;
    let imageRefreshTimer = null;
    let lastHandledEventKey = "";
    let lastReloadedEventKey = "";
    let priorityResumeIndex = -1;
    let priorityCooldownUntil = 0;
    let lastPriorityEvent = null;
    let priorityNotice = null;
    let priorityAlert = null;
    let arrivalOverview = null;
    let overview = null;
    let normalViews = 0;
    let overviewIndex = 0;
    let overviewCatalogs = [];
    const overviewsEnabled = ["living", "office"].includes(rotationProfile);
    let overviewController = null;
    let overviewRequestTimer = null;
    let overviewRefreshTimer = null;
    let overviewDisposed = false;
    const manualHoldStorage = `glimpser.manual-hold.v1.${rotationProfile}`;
    const recentStorage = `glimpser.recent-scenes.v1.${rotationProfile}`;
    let manualHold = null;
    let recentScenes = [];
    try {
      const storedHold = JSON.parse(
        window.localStorage.getItem(manualHoldStorage) || "null",
      );
      const unexpired =
        storedHold &&
        (storedHold.until === null || Number(storedHold.until) > Date.now());
      if (unexpired) {
        const heldIndex = scenes.findIndex(
          (scene) =>
            scene.dataset.sceneId === storedHold.sceneId ||
            scene.dataset.heroName === storedHold.heroName,
        );
        if (heldIndex >= 0) {
          manualHold = storedHold;
          currentIndex = heldIndex;
        } else {
          window.localStorage.removeItem(manualHoldStorage);
        }
      } else if (storedHold) {
        window.localStorage.removeItem(manualHoldStorage);
      }
      const storedRecent = JSON.parse(
        window.localStorage.getItem(recentStorage) || "[]",
      );
      if (Array.isArray(storedRecent)) recentScenes = storedRecent.slice(0, 8);
    } catch {
      manualHold = null;
      recentScenes = [];
    }
    async function refreshOverviewCatalogs() {
      if (overviewDisposed) return;
      overviewController =
        typeof AbortController === "function" ? new AbortController() : null;
      overviewRequestTimer = window.setTimeout(
        () => overviewController?.abort(),
        8000,
      );
      try {
        const models = await fetchOverviewCatalogs(overviewController?.signal);
        // Failed catalogs expire instead of leaving stale camera health eligible.
        if (!overviewDisposed) overviewCatalogs = models.filter(Boolean);
      } finally {
        window.clearTimeout(overviewRequestTimer);
        if (!overviewDisposed)
          overviewRefreshTimer = window.setTimeout(
            refreshOverviewCatalogs,
            300000,
          );
      }
    }
    if (overviewsEnabled) {
      const stylesheet = document.createElement("link");
      stylesheet.rel = "stylesheet";
      stylesheet.href = "/static/css/rotation_overview.css?v=20260920";
      document.head.append(stylesheet);
      refreshOverviewCatalogs();
    }
    const prioritySeenStorage = `glimpser.priority-seen.v1.${rotationProfile}`;
    let seenPriorityEvents = new Set();
    try {
      const stored = JSON.parse(
        window.localStorage.getItem(prioritySeenStorage) || "[]",
      );
      if (Array.isArray(stored))
        seenPriorityEvents = new Set(stored.slice(-64));
    } catch {
      /* Storage must never block rotation. */
    }
    const rememberPriorityEvent = (key) => {
      seenPriorityEvents.add(key);
      seenPriorityEvents = new Set([...seenPriorityEvents].slice(-64));
      try {
        window.localStorage.setItem(
          prioritySeenStorage,
          JSON.stringify([...seenPriorityEvents]),
        );
      } catch {
        /* Keep in-memory deduplication. */
      }
    };
    const finishPriority = () => {
      const resume = priorityResumeIndex;
      priorityResumeIndex = -1;
      resetSceneInterrupt(scenes[currentIndex]);
      priorityCooldownUntil = Date.now() + 30000;
      arrivalOverview?.dispose();
      arrivalOverview = null;
      priorityAlert?.dispose();
      priorityAlert = null;
      priorityNotice?.remove();
      priorityNotice = null;
      stageShell.classList.remove("has-priority-event");
      return isSceneSuppressed(scenes[resume])
        ? nextSceneIndex(currentIndex)
        : resume;
    };
    let queueIndices = [];
    const suppressionMs = Math.max(
      HERO_SCENE_SUPPRESSION_MIN_MS,
      rotationMs * HERO_SCENE_SUPPRESSION_MULTIPLIER,
    );
    scenes.forEach((scene) => {
      const baseRotationMs = parsePositiveInt(
        scene.dataset.landingRotationMs,
        rotationMs,
      );
      scene.dataset.landingBaseRotationMs = String(baseRotationMs);
      scene.dataset.landingRotationMs = String(baseRotationMs);
    });

    const clearExitState = () => {
      if (exitTimer) {
        window.clearTimeout(exitTimer);
        exitTimer = null;
      }
      scenes.forEach((scene) => scene.classList.remove("is-exiting"));
    };

    const clearFallbackTimer = () => {
      if (fallbackTimer) {
        window.clearTimeout(fallbackTimer);
        fallbackTimer = null;
      }
    };

    const clearRotationTimer = () => {
      if (rotationTimer) {
        window.clearTimeout(rotationTimer);
        rotationTimer = null;
      }
    };

    const clearEventPollTimer = () => {
      if (eventPollTimer) {
        window.clearInterval(eventPollTimer);
        eventPollTimer = null;
      }
    };

    const isSceneSuppressed = (scene) =>
      scene?.dataset.landingFeedUnavailable === "true" ||
      Number.parseInt(scene?.dataset.landingSuppressedUntil || "0", 10) >
        Date.now();

    const refreshQueue = () => {
      queueIndices = buildLandingQueue(
        scenes,
        currentIndex,
        isSceneSuppressed,
        LANDING_PREVIEW_QUEUE_LENGTH,
      );
    };

    const sceneRotationMs = (scene) =>
      parsePositiveInt(scene?.dataset.landingRotationMs, rotationMs);

    const resetSceneInterrupt = (scene) => {
      if (!scene) return;
      scene.dataset.landingRotationMs =
        scene.dataset.landingBaseRotationMs || String(rotationMs);
      delete scene.dataset.landingEventKey;
      delete scene.dataset.landingPriorityActive;
    };

    const nextSceneIndex = (startIndex) => {
      if (queueIndices.length) {
        return queueIndices[0];
      }

      const fallbackIndex = findNextEligibleSceneIndex(
        scenes,
        startIndex,
        new Set([startIndex]),
        isSceneSuppressed,
      );
      return fallbackIndex >= 0 ? fallbackIndex : startIndex;
    };

    const reviewControls = shell.querySelector(
      "[data-landing-review-controls]",
    );
    const reviewStatus = reviewControls?.querySelector("[data-review-status]");
    const reviewDuration = reviewControls?.querySelector(
      "[data-review-duration]",
    );
    const recentStrip = reviewControls?.querySelector("[data-review-recent]");
    const holdButton = reviewControls?.querySelector(
      '[data-review-action="hold"]',
    );

    const isManualHoldActive = () => {
      if (!manualHold) return false;
      if (manualHold.until === null || Number(manualHold.until) > Date.now())
        return true;
      manualHold = null;
      try {
        window.localStorage.removeItem(manualHoldStorage);
      } catch {
        /* Storage restrictions must not stop rotation. */
      }
      return false;
    };

    const updateReviewControls = () => {
      const active = isManualHoldActive();
      if (holdButton) {
        holdButton.textContent = active ? "Resume" : "Hold";
        holdButton.dataset.active = String(active);
        holdButton.setAttribute("aria-pressed", String(active));
        holdButton.setAttribute("aria-keyshortcuts", "Space");
        holdButton.title = active
          ? "Resume rotation (Space)"
          : "Hold this scene (Space)";
      }
      if (reviewStatus) {
        if (!active) reviewStatus.textContent = "";
        else if (manualHold.until === null) reviewStatus.textContent = "Held";
        else {
          const remainingMinutes = Math.max(
            1,
            Math.ceil((Number(manualHold.until) - Date.now()) / 60000),
          );
          reviewStatus.textContent = `Held · ${remainingMinutes}m`;
        }
      }
    };

    const persistManualHold = () => {
      if (!manualHold) return;
      const scene = scenes[currentIndex];
      manualHold.sceneId = scene?.dataset.sceneId || "";
      manualHold.heroName = scene?.dataset.heroName || "";
      try {
        window.localStorage.setItem(
          manualHoldStorage,
          JSON.stringify(manualHold),
        );
      } catch {
        /* An in-memory hold is still useful when storage is unavailable. */
      }
    };

    const clearManualHoldTimer = () => {
      if (manualHoldTimer) {
        window.clearTimeout(manualHoldTimer);
        manualHoldTimer = null;
      }
    };

    const resumeManualHold = () => {
      clearManualHoldTimer();
      manualHold = null;
      try {
        window.localStorage.removeItem(manualHoldStorage);
      } catch {
        /* Rotation can resume without storage cleanup. */
      }
      updateReviewControls();
      render();
    };

    const armManualHoldTimer = () => {
      clearManualHoldTimer();
      if (!manualHold || manualHold.until === null) return;
      const remainingMs = Math.max(0, Number(manualHold.until) - Date.now());
      manualHoldTimer = window.setTimeout(resumeManualHold, remainingMs);
    };

    const startManualHold = (durationValue) => {
      const durationMs = Number.parseInt(String(durationValue || ""), 10);
      manualHold = {
        until:
          String(durationValue) === "forever" || !Number.isFinite(durationMs)
            ? null
            : Date.now() + durationMs,
      };
      persistManualHold();
      clearRotationTimer();
      stopTimelapse();
      armManualHoldTimer();
      updateReviewControls();
    };

    const rememberRecentScene = (scene) => {
      const entry = {
        sceneId: scene?.dataset.sceneId || "",
        heroName: scene?.dataset.heroName || "",
      };
      if (!entry.sceneId && !entry.heroName) return;
      recentScenes = [
        entry,
        ...recentScenes.filter(
          (item) =>
            item.sceneId !== entry.sceneId || item.heroName !== entry.heroName,
        ),
      ].slice(0, 8);
      try {
        window.localStorage.setItem(
          recentStorage,
          JSON.stringify(recentScenes),
        );
      } catch {
        /* Keep a session-only history when storage is unavailable. */
      }
    };

    const renderRecentStrip = () => {
      if (!recentStrip) return;
      recentStrip.replaceChildren();
      recentScenes.slice(0, 6).forEach((entry) => {
        const button = document.createElement("button");
        button.type = "button";
        button.dataset.reviewSceneId = entry.sceneId;
        button.dataset.reviewHeroName = entry.heroName;
        button.textContent = entry.heroName || entry.sceneId || "Recent scene";
        recentStrip.append(button);
      });
      if (!recentStrip.childElementCount) {
        const empty = document.createElement("span");
        empty.textContent = "No recent scenes yet";
        recentStrip.append(empty);
      }
    };

    const manualNavigate = (targetIndex, holdForReview = false) => {
      if (targetIndex < 0 || targetIndex >= scenes.length) return;
      if (priorityResumeIndex >= 0) finishPriority();
      previousIndex = currentIndex;
      currentIndex = targetIndex;
      if (holdForReview && !isManualHoldActive()) startManualHold("300000");
      if (isManualHoldActive()) persistManualHold();
      render();
    };

    const navigationHistory = [];
    const previousSceneIndex = () => {
      if (navigationHistory.length > 1) {
        navigationHistory.pop();
        while (navigationHistory.length) {
          const candidate = navigationHistory[navigationHistory.length - 1];
          if (!isSceneSuppressed(scenes[candidate])) return candidate;
          navigationHistory.pop();
        }
      }
      for (let offset = 1; offset < scenes.length; offset++) {
        const candidate =
          (currentIndex - offset + scenes.length) % scenes.length;
        if (!isSceneSuppressed(scenes[candidate])) return candidate;
      }
      return currentIndex;
    };

    const handleReviewClick = (event) => {
      const recentButton = event.target.closest("[data-review-scene-id]");
      if (recentButton) {
        const targetIndex = scenes.findIndex(
          (scene) =>
            scene.dataset.sceneId === recentButton.dataset.reviewSceneId ||
            scene.dataset.heroName === recentButton.dataset.reviewHeroName,
        );
        recentStrip.hidden = true;
        manualNavigate(targetIndex, true);
        return;
      }
      const action = event.target.closest("[data-review-action]")?.dataset
        .reviewAction;
      if (action === "previous") manualNavigate(previousSceneIndex());
      if (action === "next") manualNavigate(nextSceneIndex(currentIndex));
      if (action === "hold") {
        if (isManualHoldActive()) resumeManualHold();
        else startManualHold(reviewDuration?.value || "300000");
      }
      if (action === "recent" && recentStrip) {
        renderRecentStrip();
        recentStrip.hidden = !recentStrip.hidden;
      }
    };
    const handleReviewKey = (event) => {
      if (
        event.defaultPrevented ||
        event.repeat ||
        event.altKey ||
        event.ctrlKey ||
        event.metaKey ||
        event.shiftKey
      )
        return;
      if (
        event.target?.closest?.(
          "input, select, textarea, [contenteditable]:not([contenteditable='false'])",
        )
      )
        return;
      if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
        event.preventDefault();
        manualNavigate(
          event.key === "ArrowLeft"
            ? previousSceneIndex()
            : nextSceneIndex(currentIndex),
        );
      } else if (
        event.key === " " &&
        !event.target?.closest?.("button, a, [role='button']")
      ) {
        event.preventDefault();
        if (isManualHoldActive()) resumeManualHold();
        else startManualHold(reviewDuration?.value || "300000");
      }
    };
    for (const [action, key] of [
      ["previous", "ArrowLeft"],
      ["next", "ArrowRight"],
    ]) {
      const button = reviewControls?.querySelector(
        `[data-review-action="${action}"]`,
      );
      button?.setAttribute("aria-keyshortcuts", key);
      if (button)
        button.title = `${action === "previous" ? "Previous scene" : "Next scene"} (${key === "ArrowLeft" ? "←" : "→"})`;
    }
    document.addEventListener("keydown", handleReviewKey);
    reviewControls?.addEventListener("click", handleReviewClick);
    if (isManualHoldActive()) armManualHoldTimer();
    updateReviewControls();

    const holdRotation = (reason) => {
      stopTimelapse();
      clearFallbackTimer();
      clearRotationTimer();
      clearExitState();
      overview?.dispose();
      overview = null;
      if (priorityResumeIndex >= 0) finishPriority();
      scenes.forEach((scene) => syncSceneVideo(scene, false));
      continuity.hold(reason);
    };

    const advanceFromWeakScene = (sceneIndex) => {
      if (disposed || sceneIndex !== currentIndex) return;
      scenes[sceneIndex].dataset.landingSuppressedUntil = String(
        Date.now() + suppressionMs,
      );
      holdRotation("Camera image unavailable. Retrying automatically…");
    };

    const evaluateCurrentScene = (sceneIndex = currentIndex) => {
      if (disposed || sceneIndex !== currentIndex) return;
      const scene = scenes[sceneIndex];
      const image = scene?.querySelector(".landing-hero-media img");
      if (!image?.naturalWidth || !image.complete) return;
      let lowLight = false;
      try {
        lowLight =
          JSON.parse(
            image.dataset.expectedSourceFreshness ||
              scene.dataset.heroSourceFreshness ||
              scene.querySelector("[data-source-freshness]")?.dataset
                .sourceFreshness ||
              "{}",
          ).low_light === true;
      } catch {
        /* Unknown source metadata. */
      }
      if (hasUsableImageFrame(image) === false && !lowLight) {
        advanceFromWeakScene(sceneIndex);
        return;
      }
      clearFallbackTimer();
      commitLoadedCapture(image);
      continuity.remember(image, scene);
      delete scene.dataset.landingSuppressedUntil;
      if (
        continuity.active &&
        metadataHealthy &&
        scene.dataset.landingFeedUnavailable !== "true"
      ) {
        continuity.recover();
        clearRotationTimer();
        if (!document.hidden && scenes.length > 1 && !isManualHoldActive())
          rotationTimer = window.setTimeout(rotate, sceneRotationMs(scene));
        syncSceneVideo(scene, scene.dataset.landingPriorityActive !== "true");
      }
      if (
        !livePilot &&
        !continuity.active &&
        !isManualHoldActive() &&
        metadataHealthy &&
        !document.hidden &&
        !overview &&
        !isSceneSuppressed(scene) &&
        (priorityResumeIndex >= 0 || !timelapse) &&
        preferCurrentView(
          timelapseDue,
          lastHistoryAttemptAt,
          lastLiveAt,
          priorityResumeIndex >= 0,
        ) &&
        livePilotEligible(scene, rotationProfile) &&
        (priorityResumeIndex >= 0 ||
          lastLiveAt === null ||
          Date.now() - lastLiveAt >= LIVE_INTERVAL_MS)
      ) {
        stopTimelapse();
        syncSceneVideo(scene, false);
        lastLiveAt = Date.now();
        livePilot = mountKioskLive(scene, {
          onReady: () => {
            clearRotationTimer();
            if (priorityResumeIndex >= 0) priorityAlert?.holdLive(45000);
            rotationTimer = window.setTimeout(
              rotate,
              priorityResumeIndex >= 0 ? 45000 : 30000,
            );
          },
        });
      }
      if (
        !livePilot &&
        timelapseDue &&
        !continuity.active &&
        !isManualHoldActive() &&
        metadataHealthy &&
        !document.hidden &&
        priorityResumeIndex < 0 &&
        !overview &&
        !isSceneSuppressed(scene)
      ) {
        timelapseDue = false;
        lastHistoryAttemptAt = Date.now();
        timelapse = mountTimelapse(scene.dataset.heroName, scene, {
          onReady: (duration) => {
            lastTimelapseAt = Date.now();
            syncSceneVideo(scene, false);
            clearRotationTimer();
            rotationTimer = window.setTimeout(
              rotate,
              timelapseSceneDwellMs(sceneRotationMs(scene), duration),
            );
          },
        });
      }
    };

    const render = () => {
      sceneShownAt = Date.now();
      if (navigationHistory[navigationHistory.length - 1] !== currentIndex) {
        navigationHistory.push(currentIndex);
        if (navigationHistory.length > 64) navigationHistory.shift();
      }
      stopTimelapse();
      if (priorityResumeIndex < 0 && !continuity.active)
        timelapseDue = timelapseIsDue(lastTimelapseAt);
      overview?.dispose();
      overview = null;
      clearExitState();
      clearFallbackTimer();
      clearRotationTimer();
      if (previousIndex >= 0 && previousIndex !== currentIndex) {
        resetSceneInterrupt(scenes[previousIndex]);
      }
      refreshQueue();
      syncSceneQueueSlots(scenes[currentIndex], scenes, queueIndices);
      showLandingScene(scenes, currentIndex, previousIndex);
      rememberRecentScene(scenes[currentIndex]);
      if (
        !continuity.active &&
        priorityResumeIndex < 0 &&
        !timelapseDue &&
        Date.now() - lastTimelapseAt >=
          TIMELAPSE_INTERVAL_MS - TIMELAPSE_PRELOAD_LEAD_MS
      ) {
        preloadTimelapse(scenes[queueIndices[0]]?.dataset.heroName);
      }
      if (continuity.active)
        scenes.forEach((scene) => syncSceneVideo(scene, false));
      rememberOfficeRotation(
        scenes[
          priorityResumeIndex >= 0
            ? priorityResumeIndex
            : (queueIndices[0] ?? currentIndex)
        ],
        rotationProfile,
      );
      if (previousIndex >= 0 && previousIndex !== currentIndex) {
        const staleIndex = previousIndex;
        exitTimer = window.setTimeout(() => {
          scenes[staleIndex]?.classList.remove("is-exiting");
          scenes[staleIndex].style.display = "none";
          syncSceneImages(scenes[staleIndex], false);
        }, LANDING_SCENE_EXIT_MS);
      }
      updateTimeLabels(shell);
      evaluateCurrentScene(currentIndex);
      const hero = scenes[currentIndex].querySelector(
        ".landing-hero-media img",
      );
      if (hero && (!hero.complete || !hero.naturalWidth)) {
        fallbackTimer = window.setTimeout(() => {
          fallbackTimer = null;
          if (!hero.complete || !hero.naturalWidth)
            advanceFromWeakScene(currentIndex);
        }, 8000);
      }
      if (
        scenes.length > 1 &&
        !document.hidden &&
        !continuity.active &&
        (!isManualHoldActive() || priorityResumeIndex >= 0)
      ) {
        rotationTimer = window.setTimeout(
          rotate,
          sceneRotationMs(scenes[currentIndex]),
        );
      }
    };

    const advanceRotation = () => {
      previousIndex = currentIndex;
      currentIndex =
        priorityResumeIndex >= 0
          ? finishPriority()
          : nextSceneIndex(currentIndex);
      refreshQueue();
      render();
    };

    const rotate = () => {
      if (
        document.hidden ||
        scenes.length < 2 ||
        continuity.active ||
        disposed ||
        (isManualHoldActive() && priorityResumeIndex < 0)
      )
        return;
      if (priorityResumeIndex < 0 && overviewsEnabled && ++normalViews >= 8) {
        normalViews = 0;
        const selection = chooseOverview(
          scenes,
          overviewCatalogs,
          isSceneSuppressed,
          overviewIndex,
        );
        if (selection) {
          overviewIndex++;
          clearFallbackTimer();
          stopTimelapse();
          overview = createOverview(
            selection,
            stageShell,
            () => {
              scenes.forEach((scene) => syncSceneVideo(scene, false));
            },
            () => {
              overview = null;
              advanceRotation();
            },
          );
          return;
        }
      }
      advanceRotation();
    };

    const reloadForEvent = (eventData) => {
      if (!eventData?.key || eventData.key === lastReloadedEventKey) {
        return;
      }
      try {
        const storageKey = `glimpser.event-reload.${rotationProfile}`;
        if (window.sessionStorage.getItem(storageKey) === eventData.key) return;
        window.sessionStorage.setItem(storageKey, eventData.key);
      } catch {
        return;
      }
      lastReloadedEventKey = eventData.key;
      window.location.reload();
    };

    const priorityBlocked = (event) =>
      event.priority &&
      (seenPriorityEvents.has(event.key) ||
        ((priorityResumeIndex >= 0 || Date.now() < priorityCooldownUntil) &&
          !canHandoffToDoor(event, lastPriorityEvent)));

    const activateEvent = (eventData) => {
      if (
        continuity.active ||
        !eventData?.key ||
        (isManualHoldActive() && !eventData.priority) ||
        !canInterruptScene(
          eventData.priority,
          sceneShownAt,
          sceneRotationMs(scenes[currentIndex]),
        )
      ) {
        return;
      }

      if (priorityBlocked(eventData)) return;
      const targetIndex = scenes.findIndex((scene) =>
        eventData.camera_name
          ? scene.dataset.heroName === eventData.camera_name
          : scene.dataset.sceneId === (eventData.scene_id || eventData.sceneId),
      );
      if (targetIndex < 0) {
        if (eventData.level !== "notice") {
          reloadForEvent(eventData);
        }
        return;
      }

      stopTimelapse();
      const targetScene = scenes[targetIndex];
      if (isSceneSuppressed(targetScene)) return;
      // Release the old live alert and preserve where normal rotation resumes.
      const handoffResume = priorityResumeIndex >= 0 ? finishPriority() : -1;
      overview?.dispose();
      overview = null;
      const interruptMs = parsePositiveInt(
        eventData.interrupt_ms || eventData.interruptMs,
        rotationMs,
      );
      const baseRotationMs = parsePositiveInt(
        targetScene.dataset.landingBaseRotationMs,
        rotationMs,
      );
      targetScene.dataset.landingRotationMs = String(
        eventData.priority
          ? Math.min(interruptMs, 30000)
          : Math.max(baseRotationMs, interruptMs),
      );
      targetScene.dataset.landingEventKey = eventData.key;

      refreshVisibleImages(targetScene);

      if (
        targetIndex === currentIndex &&
        eventData.key === lastHandledEventKey
      ) {
        render();
        return;
      }

      if (eventData.priority) {
        targetScene.dataset.landingPriorityActive = "true";
        lastPriorityEvent = eventData;
        priorityResumeIndex =
          handoffResume >= 0
            ? handoffResume
            : targetIndex === currentIndex
              ? nextSceneIndex(currentIndex)
              : currentIndex;
        rememberPriorityEvent(eventData.key);
        priorityAlert = createPriorityAlert(
          eventData,
          Math.min(interruptMs, 30000),
          () => {
            if (priorityResumeIndex < 0) return;
            previousIndex = currentIndex;
            currentIndex = finishPriority();
            render();
          },
        );
        priorityNotice = priorityAlert.node;
        stageShell.append(priorityNotice);
        stageShell.classList.add("has-priority-event");
        if (eventData.kind === "arrival" && eventData.cameras?.length >= 2) {
          let ready = false;
          arrivalOverview = createOverview(
            {
              label: "Arrival",
              title: `${eventData.subject_label} arrived · Entrance cameras`,
              cameras: eventData.cameras,
              duration: Math.min(interruptMs, 30000),
            },
            stageShell,
            () => {
              ready = true;
              priorityNotice?.remove();
            },
            () => {
              if (!ready || priorityResumeIndex < 0) return;
              previousIndex = currentIndex;
              currentIndex = finishPriority();
              render();
            },
          );
        }
      }
      lastHandledEventKey = eventData.key;
      previousIndex = currentIndex;
      currentIndex = targetIndex;
      refreshQueue();
      render();
    };

    const syncAvailableCameras = (available) => {
      if (
        !Array.isArray(available) ||
        !["living", "office"].includes(rotationProfile)
      )
        return;
      const names = new Set(available);
      scenes.forEach((scene) => {
        scene.dataset.landingFeedUnavailable = String(
          !names.has(scene.dataset.heroName),
        );
      });
      refreshQueue();
      // Never fall back to cycling through the same rejected cameras.
      const candidate = scenes.findIndex((scene) => !isSceneSuppressed(scene));
      if (candidate < 0) {
        holdRotation("No healthy camera feeds. Retrying automatically…");
        return;
      }
      if (isSceneSuppressed(scenes[currentIndex])) {
        if (priorityResumeIndex >= 0) finishPriority();
        previousIndex = currentIndex;
        currentIndex = candidate;
        render();
      }
    };

    const pollLandingEvents = async () => {
      if (
        disposed ||
        !eventsEnabled ||
        !eventsUrl ||
        document.hidden ||
        eventPollInFlight
      ) {
        return;
      }

      eventPollInFlight = true;
      const controller =
        typeof AbortController === "function" ? new AbortController() : null;
      const requestTimer = window.setTimeout(() => {
        controller?.abort();
        if (!disposed) {
          metadataHealthy = false;
          holdRotation("Connection timed out. Retrying automatically…");
        }
      }, 4000);
      try {
        const separator = eventsUrl.includes("?") ? "&" : "?";
        const response = await window.fetch(
          `${eventsUrl}${separator}_ts=${Date.now()}`,
          {
            cache: "no-store",
            signal: controller?.signal,
            credentials: "same-origin",
            headers: {
              Accept: "application/json",
            },
          },
        );
        if (!response.ok) throw new Error("Feed request failed");
        const payload = await response.json();
        if (disposed) return;
        if (!payload || !Array.isArray(payload.events))
          throw new Error("Invalid feed response");
        metadataHealthy = true;
        syncAvailableCameras(payload?.available_cameras);

        if (
          overview?.cameras.some((camera) => isSceneSuppressed(camera.scene))
        ) {
          overview.dispose();
          overview = null;
          advanceRotation();
        }
        if (
          payload?.capture_times &&
          typeof payload.capture_times === "object"
        ) {
          scenes.forEach((scene) => {
            const timestamp = payload.capture_times[scene.dataset.heroName];
            if (typeof timestamp !== "string" || !timestamp) return;
            const changed = updateSceneCaptureMetadata(
              scene,
              timestamp,
              payload?.source_freshness?.[scene.dataset.heroName],
            );
            if (changed && scene.classList.contains("is-visible"))
              refreshVisibleImages(scene);
          });
          updateTimeLabels(shell);
        }
        if (
          continuity.active &&
          scenes[currentIndex].dataset.landingFeedUnavailable !== "true"
        )
          refreshVisibleImages(scenes[currentIndex]);
        const eventData = Array.isArray(payload?.events)
          ? payload.events.find(
              (event) =>
                event?.key &&
                (event.priority
                  ? !priorityBlocked(event)
                  : event.key !== lastHandledEventKey),
            )
          : null;
        if (!eventData?.key || eventData.key === lastHandledEventKey) {
          // A still can load before metadata recovers. Revisit live eligibility
          // even when no timelapse is due, without disturbing an overview/hold.
          if ((timelapseDue || !livePilot) && !continuity.active && !overview)
            evaluateCurrentScene(currentIndex);
          return;
        }
        activateEvent(eventData);
      } catch {
        if (!disposed) {
          metadataHealthy = false;
          holdRotation("Connection lost. Retrying automatically…");
        }
      } finally {
        window.clearTimeout(requestTimer);
        eventPollInFlight = false;
      }
    };

    scenes.forEach((scene, sceneIndex) => {
      const image = scene.querySelector(".landing-hero-media img");
      if (!image || image.dataset.landingProbeBound === "true") {
        return;
      }
      image.dataset.landingProbeBound = "true";
      image.addEventListener("load", () => evaluateCurrentScene(sceneIndex));
      image.addEventListener("error", () => advanceFromWeakScene(sceneIndex));
      image.addEventListener("landing-image-failed", () =>
        advanceFromWeakScene(sceneIndex),
      );
    });

    // Portrait wall cams look broken when forced through the same full-bleed
    // cover treatment as skyline shots, so switch tall media into a contained
    // presentation as soon as we know the real capture dimensions.
    shell
      .querySelectorAll(
        ".landing-hero-media img, .landing-pip-card img, .landing-deck-card img",
      )
      .forEach((image) => bindImageFit(image));

    const cleanupChromeAutoHide = initChromeAutoHide(shell, chromeFadeMs);
    render();

    // Reduced-motion users still need the channel to progress. Keep rotation
    // active and reserve the preference for softer visual treatment only.
    timeTimer = window.setInterval(() => {
      updateTimeLabels(shell);
      continuity.update();
      updateReviewControls();
    }, LANDING_TIME_REFRESH_MS);
    if (imageRefreshMs > 0) {
      imageRefreshTimer = window.setInterval(() => {
        if (document.hidden) return;
        refreshVisibleImages(scenes[currentIndex]);
      }, imageRefreshMs);
    }
    if (eventsEnabled && eventsUrl && eventPollMs > 0) {
      pollLandingEvents();
      eventPollTimer = window.setInterval(pollLandingEvents, eventPollMs);
    }

    const handleVisibilityChange = () => {
      if (document.hidden) {
        stopTimelapse();
        overview?.dispose();
        overview = null;
        clearRotationTimer();
        scenes.forEach((scene) => syncSceneVideo(scene, false));
        return;
      }
      clearRotationTimer();
      if (continuity.active || isManualHoldActive()) {
        pollLandingEvents();
        return;
      }
      syncSceneVideo(
        scenes[currentIndex],
        scenes[currentIndex].dataset.landingPriorityActive !== "true",
      );
      if (scenes.length > 1) {
        rotationTimer = window.setTimeout(
          rotate,
          sceneRotationMs(scenes[currentIndex]),
        );
      }
    };
    document.addEventListener("visibilitychange", handleVisibilityChange);
    const handleOffline = () => {
      metadataHealthy = false;
      holdRotation("Network offline. Retrying automatically…");
    };
    const handleOnline = () => {
      if (eventsEnabled) pollLandingEvents();
      else {
        metadataHealthy = true;
        refreshVisibleImages(scenes[currentIndex]);
      }
    };
    window.addEventListener("offline", handleOffline);
    window.addEventListener("online", handleOnline);
    if (navigator.onLine === false) handleOffline();

    window.addEventListener(
      "pagehide",
      () => {
        disposed = true;
        stopTimelapse();
        continuity.dispose();
        window.removeEventListener("offline", handleOffline);
        window.removeEventListener("online", handleOnline);
        cleanupLandingViewportHeight();
        cleanupLandingViewportBeacon();
        cleanupChromeAutoHide();
        reviewControls?.removeEventListener("click", handleReviewClick);
        document.removeEventListener("keydown", handleReviewKey);
        clearExitState();
        clearFallbackTimer();
        clearRotationTimer();
        clearManualHoldTimer();
        clearEventPollTimer();
        arrivalOverview?.dispose();
        priorityAlert?.dispose();
        overview?.dispose();
        overviewDisposed = true;
        window.clearTimeout(overviewRefreshTimer);
        overviewController?.abort();
        window.clearTimeout(overviewRequestTimer);
        document.removeEventListener(
          "visibilitychange",
          handleVisibilityChange,
        );
        scenes.forEach((scene) => {
          scene
            .querySelectorAll("img")
            .forEach((image) => image._landingCancelRefresh?.());
          const video = scene.querySelector(".landing-hero-video");
          clearSceneVideoProbe(video);
        });
        if (timeTimer) {
          window.clearInterval(timeTimer);
        }
        if (imageRefreshTimer) {
          window.clearInterval(imageRefreshTimer);
        }
      },
      { once: true },
    );
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", setup, { once: true });
  } else {
    setup();
  }
}
