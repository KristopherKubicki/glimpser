import {
  chooseHighlight,
  createHighlight,
} from "./tv_highlights.js?v=20261015-setup-timeout";
import {
  mountRoomComfort,
  prepareSceneComfort,
} from "./room_comfort.js?v=20261009-night-clamp";
import { mountKioskIndicators } from "./kiosk_indicators.js?v=20261014-contact-reasons";
import { canHandoffToDoor } from "./priority_handoff.js";
import { simplifyDashboardHud } from "./dashboard_hud.js?v=20260926-1";
import { mountKioskHeartbeat } from "./kiosk_heartbeat.js?v=20261014-playback-frames";
import {
  livePilotEligible,
  mountKioskLive,
  liveStreamLimit,
  LIVE_INTERVAL_MS,
  LIVE_CANDIDATE_CAMERAS,
  STORE_LIVE_CAMERAS,
} from "./kiosk_live.js?v=20261017-media-lifecycle";
import {
  mountTimelapse,
  preloadTimelapse,
  cancelTimelapsePreload,
  timelapseIsDue,
  timelapseEligible,
  scenicEligible,
  SCENIC_CAMERAS,
  preferCurrentView,
  TIMELAPSE_INTERVAL_MS,
  TIMELAPSE_PRELOAD_LEAD_MS,
} from "./timelapse_preview.js?v=20261017-media-lifecycle";
import { createKioskHold } from "./kiosk_hold.js";
import {
  chooseOverview,
  withOfficeTelevision,
  overviewFollowupIndex,
  createOverview,
  fetchOverviewCatalogs,
} from "./rotation_overview.js?v=20261017-store-coverage";
import { createPriorityAlert } from "./priority_alert.js?v=20261017-media-lifecycle";
import { captureImageUrl, captureAge, captionAge } from "./capture_age.js";
import { formatExactTime, timeAgo } from "./time_utils.js";

if (!document.querySelector("link[data-rotator-review-style]")) {
  const style = document.createElement("link");
  style.rel = "stylesheet";
  style.href = "/static/css/rotator_review.css?v=20261016-back";
  style.dataset.rotatorReviewStyle = "";
  document.head.append(style);
}

if (!document.querySelector("link[data-priority-alert-style]")) {
  const style = document.createElement("link");
  style.rel = "stylesheet";
  style.href = "/static/css/priority_alert.css?v=20261015-handoff";
  style.dataset.priorityAlertStyle = "";
  document.head.append(style);
}

if (!document.querySelector("link[data-kiosk-live-style]")) {
  const style = document.createElement("link");
  style.rel = "stylesheet";
  style.href = "/static/css/kiosk_live.css?v=20261017-compositor";
  style.dataset.kioskLiveStyle = "";
  document.head.append(style);
}

// Require consecutive catalog observations before replacing a running wall.
// Removals are handled in place; only additions need server-rendered scenes.
export function createCatalogChangeTracker(renderedNames) {
  const rendered = new Set(renderedNames);
  let candidate = "";
  return (available) => {
    if (
      !Array.isArray(available) ||
      available.some((name) => typeof name !== "string" || !name.trim())
    ) {
      candidate = "";
      return false;
    }
    const additions = [...new Set(available)]
      .filter((name) => !rendered.has(name))
      .sort();
    const next = additions.length ? JSON.stringify(additions) : "";
    const confirmed = Boolean(next && next === candidate);
    candidate = next;
    return confirmed;
  };
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
const LANDING_SCENE_EXIT_MS = 3300;
const LANDING_TIME_REFRESH_MS = 60000;
const LANDING_PROGRESS_CHECK_MS = 5000;
const LANDING_MEANINGFUL_VIEW_MS = 8000;
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

export function initChromeAutoHide(shell, hideAfterMs) {
  if (!shell || hideAfterMs <= 0) return () => {};

  let chromeTimer = null;
  let reviewPointerActive = false;

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
        reviewPointerActive ||
        shell.querySelector("[data-review-recent]:not([hidden])") ||
        (shell.contains(focused) &&
          focused?.matches(
            ":focus-visible, input, select, textarea, [contenteditable='true']",
          ))
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

  const holdReviewChrome = (event) => {
    reviewPointerActive = Boolean(
      event.target?.closest?.("[data-landing-review-controls]"),
    );
    revealChrome();
  };
  const releaseReviewChrome = () => {
    reviewPointerActive = false;
    scheduleHide();
  };
  shell.addEventListener("pointerdown", holdReviewChrome, { passive: true });
  for (const name of ["pointerup", "pointercancel", "blur"])
    window.addEventListener(name, releaseReviewChrome);

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
    shell.removeEventListener("pointerdown", holdReviewChrome);
    for (const name of ["pointerup", "pointercancel", "blur"])
      window.removeEventListener(name, releaseReviewChrome);
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
    if (isVisible && !scene.classList.contains("is-visible")) {
      scene.classList.remove("is-exiting");
      scene.style.display = "";
      prepareSceneComfort(scene);
      // Commit the hidden start state. display:none -> visible in one style
      // update skips CSS transitions and exposes bright pages in one frame.
      void scene.offsetWidth;
    }
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

// Save upcoming camera names rather than positions: health changes reorder the pool.
export function restoreOfficeRotation(scenes, profile) {
  if (!["office", "living", "hal"].includes(profile)) return -1;
  try {
    const nextCamera = window.localStorage.getItem(
      `glimpser.${profile}.next-camera.v1`,
    );
    const primary = scenes.findIndex(
      (scene) => scene.dataset.heroName === nextCamera,
    );
    if (primary >= 0) return primary;
    const upcoming = JSON.parse(
      window.localStorage.getItem(`glimpser.${profile}.upcoming-cameras.v1`) ||
        "[]",
    );
    if (!Array.isArray(upcoming)) return -1;
    // If the next feed disappeared, continue to its next surviving neighbor.
    for (const name of upcoming.slice(0, 12)) {
      if (typeof name !== "string") continue;
      const index = scenes.findIndex(
        (scene) => scene.dataset.heroName === name,
      );
      if (index >= 0) return index;
    }
    return -1;
  } catch {
    return -1;
  }
}

export function rememberOfficeRotation(scene, profile, scenes = []) {
  if (
    !["office", "living", "hal"].includes(profile) ||
    !scene?.dataset.heroName
  )
    return;
  try {
    window.localStorage.setItem(
      `glimpser.${profile}.next-camera.v1`,
      scene.dataset.heroName,
    );
    const start = scenes.findIndex(
      (candidate) => candidate.dataset.heroName === scene.dataset.heroName,
    );
    const upcoming =
      start < 0
        ? [scene.dataset.heroName]
        : Array.from(
            { length: Math.min(12, scenes.length) },
            (_, offset) =>
              scenes[(start + offset) % scenes.length].dataset.heroName,
          ).filter((name) => typeof name === "string" && name.length > 0);
    window.localStorage.setItem(
      `glimpser.${profile}.upcoming-cameras.v1`,
      JSON.stringify(upcoming),
    );
  } catch {
    // Storage restrictions must never stop the display from rotating.
  }
}

// Reconcile health without resetting progress when the current feed disappears.
export function updateLandingAvailability(
  scenes,
  currentIndex,
  available,
  profile,
  isSuppressed,
) {
  if (
    !Array.isArray(available) ||
    !["living", "office", "hal"].includes(profile)
  )
    return null;
  const names = new Set(available);
  scenes.forEach((scene) => {
    scene.dataset.landingFeedUnavailable = String(
      !names.has(scene.dataset.heroName),
    );
  });
  if (scenes[currentIndex] && !isSuppressed(scenes[currentIndex]))
    return currentIndex;
  // The preview-queue helper deliberately permits weak-frame fallbacks.
  // Health reconciliation must never choose a known-unavailable fallback.
  for (let offset = 1; offset < scenes.length; offset++) {
    const next = (currentIndex + offset) % scenes.length;
    if (!isSuppressed(scenes[next])) return next;
  }
  return -1;
}

export function rotationCategory(scene) {
  const group = (
    scene.querySelector?.("[data-area-label]")?.dataset.areaLabel || "other"
  ).toLowerCase();
  const categories = {
    house: ["knox", "argyle", "halsted", "beachhouse", "plants", "garden"],
    systems: ["systems", "network", "hubitat", "power", "graph"],
    weather: ["weather", "sky", "radar", "satellite", "regional satellite"],
    science: ["cosmic", "science"],
    lake: ["marine", "beach", "waukegan", "winthrop", "crib"],
    world: ["tv", "news", "health", "ecom", "usa"],
    local: [
      "regional",
      "traffic",
      "lincolnwood",
      "chicago",
      "milwaukee",
      "skyline",
      "map",
      "flights",
    ],
  };
  return (
    Object.keys(categories).find((key) => categories[key].includes(group)) ||
    group
  );
}

const KNOX_EXTERIORS = new Set([
  "FrontDoor",
  "Driveway",
  "Street",
  "Garage",
  "Walkway",
  "Backyard",
  "Garden",
]);

const BEACH_LANDSCAPES = new Set([
  "BeachShore",
  "BeachSouthJetty",
  "BeachBioswale",
  "BeachGravel",
  "BeachMapleTree",
  "Beach_Google_Backyard",
  "Beach_Google_Front_Yard",
]);

const ARGYLE_ENTRY_VIEWS = new Set([
  "ArgyleEntryFisheye",
  "Argyle100",
  "Argyle200",
  "Showroom_Entrance",
  "Front_door_doorbell",
]);

function storeProperty(scene) {
  const name = scene?.dataset.heroName || "";
  if (STORE_LIVE_CAMERAS.has(name))
    return name.startsWith("Argyle") ? "argyle" : "halsted";
  if (ARGYLE_ENTRY_VIEWS.has(name)) return "argyle";
  if (name.startsWith("Halsted_Google_")) return "halsted";
  return null;
}

export function createRotationBalance(profile, storage) {
  if (!["office", "living", "hal"].includes(profile)) return null;
  const key = `glimpser.${profile}.rotation-history.v1`;
  let seen = new Map();
  let serial = 0;
  try {
    const rows = JSON.parse(storage?.getItem(key) || "[]");
    if (Array.isArray(rows)) {
      seen = new Map(
        rows
          .slice(-512)
          .filter(
            (row) =>
              Array.isArray(row) &&
              typeof row[0] === "string" &&
              Number.isSafeInteger(row[1]) &&
              row[1] > 0 &&
              row[1] < Number.MAX_SAFE_INTEGER - 10000,
          ),
      );
      serial = Math.max(0, ...seen.values());
    }
  } catch {
    /* An unavailable history never prevents rotation. */
  }
  return {
    recentlyViewed(name) {
      const last = seen.get(name);
      return last !== undefined && serial - last < 12;
    },
    viewed(scene) {
      const name = scene?.dataset.heroName;
      if (!name) return;
      seen.delete(name);
      seen.set(name, ++serial);
      seen = new Map([...seen].slice(-512));
      try {
        storage?.setItem(key, JSON.stringify([...seen]));
      } catch {
        /* Session-only fairness remains available. */
      }
    },
    queue(scenes, currentIndex, suppressed, length, historyDue = false) {
      const simulated = new Map(seen);
      let order = serial;
      let cursor = currentIndex;
      const used = new Set([currentIndex]);
      const result = [];
      while (result.length < Math.min(length, scenes.length - 1)) {
        let candidates = scenes
          .map((scene, index) => ({
            scene,
            index,
            last: simulated.get(scene.dataset.heroName) || 0,
            distance: (index - cursor + scenes.length) % scenes.length,
          }))
          .filter((item) => !used.has(item.index) && !suppressed(item.scene));
        if (ARGYLE_ENTRY_VIEWS.has(scenes[cursor]?.dataset.heroName)) {
          const otherViews = candidates.filter(
            (item) => !ARGYLE_ENTRY_VIEWS.has(item.scene.dataset.heroName),
          );
          if (otherViews.length) candidates = otherViews;
        }
        candidates.sort((a, b) => a.last - b.last || a.distance - b.distance);
        // A bounded window prevents variety from repeatedly skipping older views.
        const oldest = candidates.slice(0, 12);
        const category = rotationCategory(scenes[cursor]);
        const liveInterval =
          profile === "office" ? 2 : profile === "living" ? 3 : Infinity;
        const liveCandidates = Number.isFinite(liveInterval)
          ? candidates.filter((item) => livePilotEligible(item.scene, profile))
          : [];
        // The catalog order is stable, so always taking its first stream
        // starves other healthy entrances and exterior cameras.
        liveCandidates.sort(
          (a, b) => a.last - b.last || a.distance - b.distance,
        );
        const lastLive = Math.max(
          0,
          ...[
            ...LIVE_CANDIDATE_CAMERAS,
            ...scenes
              .filter((scene) => scene.dataset.heroMediaKind === "youtube")
              .map((scene) => scene.dataset.heroName),
          ].map((name) => simulated.get(name) || 0),
        );
        // Public broadcasts get a regular turn even when the estate has many
        // more live cameras. Oldest-viewed ordering still shares all broadcasts.
        const lastBroadcast = Math.max(
          0,
          ...scenes
            .filter((scene) => scene.dataset.heroMediaKind === "youtube")
            .map((scene) => simulated.get(scene.dataset.heroName) || 0),
        );
        const broadcastCandidate =
          order - lastBroadcast >= 6
            ? liveCandidates.find(
                (item) => item.scene.dataset.heroMediaKind === "youtube",
              )
            : null;
        const historyCandidate =
          historyDue && result.length === 0
            ? candidates
                .filter((item) => timelapseEligible(item.scene, profile))
                .sort((a, b) => a.last - b.last || a.distance - b.distance)[0]
            : null;
        // Reserve a regular exterior visit without dropping the broad queue.
        // Use least-recently shown so Street cannot lose to the same entrance.
        const lastKnox = Math.max(
          0,
          ...[...KNOX_EXTERIORS].map((name) => simulated.get(name) || 0),
        );
        const knoxCandidate =
          profile === "office" && order - lastKnox >= 4
            ? candidates.find((item) =>
                KNOX_EXTERIORS.has(item.scene.dataset.heroName),
              )
            : null;
        // A shoreline/quarry visit after six other scenes keeps landscapes
        // visible even when live entrances and house history dominate.
        const lastScenic = Math.max(
          0,
          ...[...SCENIC_CAMERAS].map((name) => simulated.get(name) || 0),
        );
        const scenicCandidate =
          order - lastScenic >= 6
            ? candidates.find((item) => scenicEligible(item.scene, profile))
            : null;
        // Regional skylines can satisfy the scenic lane indefinitely. Give
        // healthy beach-property landscapes their own frequent reservation.
        // Count actual completed views (including overview tiles), not plans.
        const lastBeach = Math.max(
          0,
          ...[...BEACH_LANDSCAPES].map((name) => simulated.get(name) || 0),
        );
        const beachCandidate =
          order - lastBeach >= (profile === "office" ? 3 : 4)
            ? candidates.find(
                (item) =>
                  BEACH_LANDSCAPES.has(item.scene.dataset.heroName) &&
                  scenicEligible(item.scene, profile),
              )
            : null;
        // Completed comparison tiles count too. Reserve a solo fallback only
        // when a site has not appeared for twelve actual camera observations.
        const storeCandidate =
          profile === "office"
            ? ["argyle", "halsted"]
                .map((site) => ({
                  last: Math.max(
                    0,
                    ...scenes
                      .filter((scene) => storeProperty(scene) === site)
                      .map(
                        (scene) => simulated.get(scene.dataset.heroName) || 0,
                      ),
                  ),
                  candidate: candidates.find(
                    (item) => storeProperty(item.scene) === site,
                  ),
                }))
                .filter((item) => item.candidate && order - item.last >= 12)
                .sort((a, b) => a.last - b.last)[0]?.candidate
            : null;
        const pick =
          storeCandidate ||
          knoxCandidate ||
          beachCandidate ||
          scenicCandidate ||
          broadcastCandidate ||
          (order - lastLive >= liveInterval && liveCandidates[0]) ||
          historyCandidate ||
          oldest.find((item) => rotationCategory(item.scene) !== category) ||
          oldest[0];
        if (!pick) break;
        result.push(pick.index);
        used.add(pick.index);
        simulated.set(pick.scene.dataset.heroName, ++order);
        cursor = pick.index;
      }
      return result;
    },
  };
}

export function rememberOverviewViews(balance, scenes, names) {
  // Only successfully displayed tiles count. Failed loads must keep their turn.
  const shown = new Set(names);
  for (const scene of scenes) {
    if (shown.delete(scene.dataset.heroName)) balance?.viewed(scene);
  }
}

export function normalizeRecentScenes(value) {
  if (!Array.isArray(value)) return [];
  return value
    .slice(0, 64)
    .filter((entry) => entry && typeof entry === "object")
    .map((entry) => ({
      sceneId: typeof entry.sceneId === "string" ? entry.sceneId : "",
      heroName: typeof entry.heroName === "string" ? entry.heroName : "",
    }))
    .filter((entry) => entry.sceneId || entry.heroName)
    .slice(0, 8);
}

export function applyLandingCaptionUpdates(scenes, updates) {
  if (!Array.isArray(updates)) return 0;
  const byCamera = new Map(
    scenes.map((scene) => [scene.dataset.heroName, scene]),
  );
  let changed = 0;
  updates.slice(0, 64).forEach((update) => {
    if (
      !update ||
      typeof update.camera_name !== "string" ||
      typeof update.caption !== "string" ||
      typeof update.caption_at !== "string" ||
      !update.caption_at
    )
      return;
    const scene = byCamera.get(update.camera_name);
    const age = scene?.querySelector("[data-caption-age]");
    const copy = scene?.querySelector(".kiosk-caption-text");
    if (!age || !copy || (age.dataset.captionAge || "") >= update.caption_at)
      return;
    copy.textContent = update.caption;
    age.dataset.captionAge = update.caption_at;
    age.textContent = captionAge(update.caption_at);
    changed++;
  });
  return changed;
}

export function initLanding({
  reloadPage = () => window.location.reload(),
} = {}) {
  const setup = () => {
    const shell = document.querySelector("[data-landing-screen]");
    if (!shell) return;

    const cleanupLandingViewportHeight = initLandingViewportHeightSync();
    const cleanupLandingViewportBeacon = initLandingViewportBeacon(shell);
    const stageShell = shell.querySelector(".landing-stage-shell") || shell;
    // Refresh membership even from an empty pool, while preserving room progress.
    const poolRefreshTimer = ["living", "office", "hal"].includes(
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
    mountRoomComfort(stageShell);
    scenes.forEach(prepareSceneComfort);
    let rotationStorage;
    try {
      rotationStorage = window.localStorage;
    } catch {
      /* Session-only history. */
    }
    const rotationBalance = createRotationBalance(
      rotationProfile,
      rotationStorage,
    );

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
    let pendingLive = null;
    let lastLiveAt = null;
    let timelapse = null;
    let lastTimelapseAt = null;
    let lastHistoryAttemptAt = null;
    let timelapseDue = false;
    const stopTimelapse = () => {
      pendingLive?.handle?.dispose();
      pendingLive = null;
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
    let eventRequest = null;
    const cancelEventRequest = () => {
      const request = eventRequest;
      eventRequest = null;
      request?.cancel();
    };
    const pageAssetRevision = stageShell.dataset.landingAssetRevision || "";
    let assetRevisionCandidate = "";
    let pendingAssetReload = false;
    let pendingCatalogReload = false;
    const catalogChanged = createCatalogChangeTracker(
      scenes.map((scene) => scene.dataset.heroName),
    );
    let timeTimer = null;
    let progressTimer = null;
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
    const overviewIndexStorage = `glimpser.overview-index.v1.${rotationProfile}`;
    let overviewIndex = 0;
    try {
      const saved = Number(window.localStorage.getItem(overviewIndexStorage));
      if (Number.isSafeInteger(saved) && saved >= 0 && saved <= 1000000)
        overviewIndex = saved;
    } catch {
      // A blocked storage API does not stop the overview cycle.
    }
    let overviewCatalogs = [];
    const overviewsEnabled = ["living", "office"].includes(rotationProfile);
    let overviewController = null;
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
    } catch {
      manualHold = null;
    }
    // A damaged recent-view list must not cancel a valid, independent hold.
    try {
      recentScenes = normalizeRecentScenes(
        JSON.parse(window.localStorage.getItem(recentStorage) || "[]"),
      );
    } catch {
      recentScenes = [];
    }
    async function refreshOverviewCatalogs() {
      if (overviewDisposed) return;
      overviewController =
        typeof AbortController === "function" ? new AbortController() : null;
      try {
        const models = await fetchOverviewCatalogs(overviewController?.signal);
        // Failed catalogs expire instead of leaving stale camera health eligible.
        if (!overviewDisposed) overviewCatalogs = models.filter(Boolean);
      } finally {
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
      stylesheet.href =
        "/static/css/rotation_overview.css?v=20261015-wide-pairs";
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
      (["youtube", "tv"].includes(scene?.dataset.heroMediaKind) &&
        Number(scene.dataset.liveRetryAfter) > Date.now()) ||
      Number.parseInt(scene?.dataset.landingSuppressedUntil || "0", 10) >
        Date.now();

    const refreshQueue = () => {
      queueIndices = rotationBalance
        ? rotationBalance.queue(
            scenes,
            currentIndex,
            isSceneSuppressed,
            LANDING_PREVIEW_QUEUE_LENGTH,
            timelapseDue && priorityResumeIndex < 0 && !continuity.active,
          )
        : buildLandingQueue(
            scenes,
            currentIndex,
            isSceneSuppressed,
            LANDING_PREVIEW_QUEUE_LENGTH,
          );
    };

    const sceneRotationMs = (scene) =>
      parsePositiveInt(scene?.dataset.landingRotationMs, rotationMs);

    // A fresh render can restart the normal timer without showing a new view.
    // Count a different scene only after it has stayed on screen long enough.
    let progressSceneIndex = currentIndex;
    let progressSceneSince = Date.now();
    let candidateSceneIndex = currentIndex;
    let candidateSceneSince = progressSceneSince;
    const checkRotationProgress = () => {
      if (candidateSceneIndex !== currentIndex) {
        candidateSceneIndex = currentIndex;
        candidateSceneSince = Date.now();
      }
      if (
        document.hidden ||
        disposed ||
        scenes.length < 2 ||
        continuity.active ||
        isManualHoldActive() ||
        priorityResumeIndex >= 0 ||
        scenes[currentIndex].classList.contains("has-timelapse") ||
        overview ||
        pendingLive ||
        arrivalOverview
      ) {
        progressSceneIndex = currentIndex;
        progressSceneSince = Date.now();
        return;
      }
      if (currentIndex !== progressSceneIndex) {
        if (Date.now() - candidateSceneSince >= LANDING_MEANINGFUL_VIEW_MS) {
          progressSceneIndex = currentIndex;
          progressSceneSince = Date.now();
        }
        return;
      }
      const rescueAfterMs = Math.min(
        120000,
        Math.max(70000, sceneRotationMs(scenes[currentIndex]) * 1.5),
      );
      if (Date.now() - progressSceneSince < rescueAfterMs) return;
      refreshQueue();
      const nextIndex = nextSceneIndex(currentIndex);
      if (nextIndex === currentIndex || isSceneSuppressed(scenes[nextIndex])) {
        progressSceneSince = Date.now();
        return;
      }
      scenes[currentIndex].dataset.landingSuppressedUntil = String(
        Date.now() + suppressionMs,
      );
      clearRotationTimer();
      rotate();
    };

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
    const recentToggle = reviewControls?.querySelector(
      '[data-review-action="recent"]',
    );
    recentToggle?.setAttribute("aria-expanded", "false");
    const holdButton = reviewControls?.querySelector(
      '[data-review-action="hold"]',
    );

    const isManualHoldActive = () => {
      if (!manualHold) return false;
      // The hold timer must resume the comparison before discarding its binding.
      if (manualHold.overview) return true;
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
          reviewStatus.textContent =
            Number(manualHold.until) - Date.now() < 60000
              ? "Held · less than a minute"
              : `Held · ${remainingMinutes}m`;
        }
      }
    };

    const persistManualHold = () => {
      if (!manualHold) return;
      if (manualHold.overview) {
        // Comparison state is session-only; never restore a hold on the solo
        // scene hidden underneath it after a reload.
        try {
          window.localStorage.removeItem(manualHoldStorage);
        } catch {
          /* Optional storage. */
        }
        return;
      }
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

    const clearManualHold = () => {
      if (manualHold?.overview) overview?.setHeld?.(false);
      clearManualHoldTimer();
      manualHold = null;
      try {
        window.localStorage.removeItem(manualHoldStorage);
      } catch {
        /* Rotation can resume without storage cleanup. */
      }
      updateReviewControls();
    };

    const disposeOverview = () => {
      if (manualHold?.overview) clearManualHold();
      overview?.dispose();
      overview = null;
    };

    const resumeManualHold = () => {
      const resumed = manualHold?.overview && overview?.setHeld?.(false);
      clearManualHold();
      if (!resumed) render();
    };

    const armManualHoldTimer = () => {
      clearManualHoldTimer();
      if (!manualHold || manualHold.until === null) return;
      const remainingMs = Math.max(0, Number(manualHold.until) - Date.now());
      manualHoldTimer = window.setTimeout(resumeManualHold, remainingMs);
    };

    const startManualHold = (durationValue, holdComparison = false) => {
      const durationMs = Number.parseInt(String(durationValue || ""), 10);
      manualHold = {
        until:
          String(durationValue) === "forever" || !Number.isFinite(durationMs)
            ? null
            : Date.now() + durationMs,
      };
      if (holdComparison && overview) {
        if (overview.setHeld?.(true)) manualHold.overview = true;
        else disposeOverview();
      }
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
        const scene = scenes.find(
          (item) =>
            item.dataset.sceneId === entry.sceneId ||
            item.dataset.heroName === entry.heroName,
        );
        if (!scene || isSceneSuppressed(scene)) return;
        const button = document.createElement("button");
        button.type = "button";
        button.dataset.reviewSceneId = entry.sceneId;
        button.dataset.reviewHeroName = entry.heroName;
        const label = document.createElement("span");
        label.textContent = entry.heroName || entry.sceneId || "Recent scene";
        const source = scene.querySelector(".landing-hero-media img");
        if (
          source?.getAttribute("src") &&
          hasUsableImageFrame(source) === true
        ) {
          const thumbnail = document.createElement("img");
          thumbnail.alt = "";
          thumbnail.src = source.currentSrc || source.src;
          thumbnail.decoding = "async";
          thumbnail.addEventListener("error", () => thumbnail.remove(), {
            once: true,
          });
          button.append(thumbnail);
        }
        button.append(label);
        recentStrip.append(button);
      });
      if (!recentStrip.childElementCount) {
        const empty = document.createElement("span");
        empty.textContent = "No recent scenes yet";
        recentStrip.append(empty);
      }
    };

    const manualNavigate = (
      targetIndex,
      holdForReview = false,
      holdMs = "300000",
    ) => {
      if (targetIndex < 0 || targetIndex >= scenes.length) return;
      if (manualHold?.overview) clearManualHold();
      if (priorityResumeIndex >= 0) finishPriority();
      previousIndex = currentIndex;
      currentIndex = targetIndex;
      if (holdForReview && (!isManualHoldActive() || manualHold?.briefReview)) {
        startManualHold(holdMs);
        manualHold.briefReview = holdMs === "30000";
      }
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
        recentToggle?.setAttribute("aria-expanded", "false");
        recentToggle?.focus({ preventScroll: true });
        manualNavigate(targetIndex, true);
        return;
      }
      const action = event.target.closest("[data-review-action]")?.dataset
        .reviewAction;
      if (action === "previous")
        manualNavigate(previousSceneIndex(), true, "30000");
      if (action === "next") manualNavigate(nextSceneIndex(currentIndex));
      if (action === "hold") {
        if (isManualHoldActive()) resumeManualHold();
        else startManualHold(reviewDuration?.value || "300000", true);
      }
      if (action === "recent" && recentStrip) {
        renderRecentStrip();
        recentStrip.hidden = !recentStrip.hidden;
        recentToggle?.setAttribute(
          "aria-expanded",
          String(!recentStrip.hidden),
        );
      }
    };
    const handleReviewKey = (event) => {
      if (
        event.defaultPrevented ||
        event.isComposing ||
        [
          ...document.querySelectorAll(
            'dialog[open], [role="dialog"][aria-modal="true"]',
          ),
        ].some(
          (modal) =>
            !modal.closest('[hidden], [aria-hidden="true"]') &&
            (typeof modal.checkVisibility === "function"
              ? modal.checkVisibility({ checkVisibilityCSS: true })
              : window.getComputedStyle(modal).display !== "none" &&
                window.getComputedStyle(modal).visibility !== "hidden"),
        ) ||
        event.repeat ||
        event.altKey ||
        event.ctrlKey ||
        event.metaKey ||
        event.shiftKey
      )
        return;
      if (
        event.target?.closest?.(
          "input, select, textarea, video[controls], audio[controls], [role='slider'], [role='tab'], [role='menuitem'], [contenteditable]:not([contenteditable='false'])",
        )
      )
        return;
      if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
        event.preventDefault();
        manualNavigate(
          event.key === "ArrowLeft"
            ? previousSceneIndex()
            : nextSceneIndex(currentIndex),
          event.key === "ArrowLeft",
          "30000",
        );
      } else if (
        event.key === " " &&
        !event.target?.closest?.("button, a, [role='button']")
      ) {
        event.preventDefault();
        if (isManualHoldActive()) resumeManualHold();
        else startManualHold(reviewDuration?.value || "300000", true);
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
      if (!continuity.active) {
        // Harvest already-decoded pictures; an outage must not require a fetch.
        scenes.slice(0, 8).forEach((scene) => {
          const image = scene.querySelector(".landing-hero-media img");
          if (image?.complete && hasUsableImageFrame(image) === true)
            continuity.remember(image, scene);
        });
      }
      cancelTimelapsePreload();
      stopTimelapse();
      clearFallbackTimer();
      clearRotationTimer();
      clearExitState();
      disposeOverview();
      if (priorityResumeIndex >= 0) finishPriority();
      scenes.forEach((scene) => syncSceneVideo(scene, false));
      continuity.hold(reason);
    };

    const advanceFromWeakScene = (sceneIndex) => {
      if (disposed || sceneIndex !== currentIndex) return;
      scenes[sceneIndex].dataset.landingSuppressedUntil = String(
        Date.now() + suppressionMs,
      );
      clearFallbackTimer();
      clearRotationTimer();
      // A rejected frame belongs to one source, not the whole kiosk. Use a
      // deferred, strict search so an all-bad queue cannot recurse or spin.
      const eligible = (scene, index) => {
        if (index === sceneIndex || isSceneSuppressed(scene)) return false;
        const image = scene.querySelector(".landing-hero-media img");
        return image?.complete && hasUsableImageFrame(image) === true;
      };
      // A bad queued frame must not bounce straight back to the just-viewed
      // scene when another healthy candidate exists.
      let candidate = scenes.findIndex(
        (scene, index) => index !== previousIndex && eligible(scene, index),
      );
      if (candidate < 0) candidate = scenes.findIndex(eligible);
      if (candidate < 0) {
        holdRotation("No usable camera images. Retrying automatically…");
        return;
      }
      fallbackTimer = window.setTimeout(() => {
        fallbackTimer = null;
        if (disposed || currentIndex !== sceneIndex) return;
        if (priorityResumeIndex >= 0) finishPriority();
        clearManualHold();
        previousIndex = currentIndex;
        currentIndex = candidate;
        render();
      }, 250);
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
        !pendingLive &&
        !continuity.active &&
        !isManualHoldActive() &&
        metadataHealthy &&
        !document.hidden &&
        !overview &&
        !isSceneSuppressed(scene) &&
        (priorityResumeIndex >= 0 || !timelapse) &&
        preferCurrentView(
          timelapseDue && timelapseEligible(scene, rotationProfile),
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
        const previousLiveAt = lastLiveAt;
        let displayedLiveFrames = false;
        lastLiveAt = Date.now();
        livePilot = mountKioskLive(scene, {
          onUnavailable: () => {
            // Let mount finish before releasing its handle; never revive an exited scene.
            window.setTimeout(() => {
              if (
                disposed ||
                scenes[currentIndex] !== scene ||
                priorityResumeIndex >= 0 ||
                !livePilot?.failed
              )
                return;
              livePilot.dispose();
              livePilot = null;
              // A failed connection is not a live viewing. Keep its per-feed
              // cooldown, but let another healthy broadcast use this turn.
              if (!displayedLiveFrames) lastLiveAt = previousLiveAt;
              timelapseDue = true;
              evaluateCurrentScene(currentIndex);
            }, 0);
          },
          onReady: () => {
            displayedLiveFrames = true;
            clearRotationTimer();
            if (priorityResumeIndex >= 0) priorityAlert?.holdLive(45000);
            rotationTimer = window.setTimeout(
              rotate,
              priorityResumeIndex >= 0
                ? 45000
                : Math.max(
                    sceneRotationMs(scene),
                    rotationProfile === "office" ? 40000 : 35000,
                  ),
            );
          },
        });
        if (scenes.length > 1 && rotationTimer !== null) {
          clearRotationTimer();
          rotationTimer = window.setTimeout(
            rotate,
            Math.max(sceneRotationMs(scene), livePilot.startupRemainingMs),
          );
        }
      }
      if (
        !livePilot &&
        !pendingLive &&
        timelapseDue &&
        !continuity.active &&
        !isManualHoldActive() &&
        metadataHealthy &&
        !document.hidden &&
        priorityResumeIndex < 0 &&
        !overview &&
        !isSceneSuppressed(scene) &&
        timelapseEligible(scene, rotationProfile)
      ) {
        timelapseDue = false;
        lastHistoryAttemptAt = Date.now();
        const releaseHistory = () => {
          window.setTimeout(() => {
            if (disposed || scenes[currentIndex] !== scene || !timelapse)
              return;
            timelapse.dispose();
            timelapse = null;
            // Completed history no longer blocks a live view of this camera.
            // Evaluation still enforces holds, visibility and stream cooldowns.
            evaluateCurrentScene(currentIndex);
          }, 0);
        };
        timelapse = mountTimelapse(scene.dataset.heroName, scene, {
          onUnavailable: releaseHistory,
          onEnded: releaseHistory,
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

    const render = (preparedLive = null) => {
      sceneShownAt = Date.now();
      if (navigationHistory[navigationHistory.length - 1] !== currentIndex) {
        navigationHistory.push(currentIndex);
        if (navigationHistory.length > 64) navigationHistory.shift();
      }
      stopTimelapse();
      if (preparedLive) {
        livePilot = preparedLive;
        livePilot.reveal();
        lastLiveAt = Date.now();
      }
      if (priorityResumeIndex < 0 && !continuity.active)
        timelapseDue = timelapseIsDue(lastTimelapseAt);
      disposeOverview();
      clearExitState();
      clearFallbackTimer();
      clearRotationTimer();
      if (previousIndex >= 0 && previousIndex !== currentIndex) {
        resetSceneInterrupt(scenes[previousIndex]);
      }
      refreshQueue();
      syncSceneQueueSlots(scenes[currentIndex], scenes, queueIndices);
      showLandingScene(scenes, currentIndex, previousIndex);
      if (preparedLive) syncSceneVideo(scenes[currentIndex], false);
      rememberRecentScene(scenes[currentIndex]);
      if (
        !continuity.active &&
        priorityResumeIndex < 0 &&
        (timelapseDue ||
          Date.now() - lastTimelapseAt >=
            TIMELAPSE_INTERVAL_MS - TIMELAPSE_PRELOAD_LEAD_MS)
      ) {
        preloadTimelapse(
          queueIndices
            .slice(0, 3)
            .map((index) => scenes[index])
            .find((scene) => timelapseEligible(scene, rotationProfile))?.dataset
            .heroName,
        );
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
        scenes,
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
      if (!preparedLive && hero && (!hero.complete || !hero.naturalWidth)) {
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
          Math.max(
            sceneRotationMs(scenes[currentIndex]),
            preparedLive ? (rotationProfile === "office" ? 40000 : 35000) : 0,
            livePilot?.startupRemainingMs || 0,
          ),
        );
      }
    };

    const reloadForAssets = () => {
      if (
        !(pendingAssetReload || pendingCatalogReload) ||
        !metadataHealthy ||
        document.hidden ||
        continuity.active ||
        isManualHoldActive() ||
        priorityResumeIndex >= 0
      )
        return false;
      pendingAssetReload = false;
      pendingCatalogReload = false;
      reloadPage();
      return true;
    };

    const advanceRotation = (relatedNames = []) => {
      if (reloadForAssets()) return;
      refreshQueue();
      const relatedIndex = overviewFollowupIndex(
        queueIndices,
        scenes,
        relatedNames,
        currentIndex,
      );
      const nextIndex =
        priorityResumeIndex >= 0
          ? finishPriority()
          : relatedIndex >= 0
            ? relatedIndex
            : nextSceneIndex(currentIndex);
      const candidate = scenes[nextIndex];
      if (
        nextIndex !== currentIndex &&
        metadataHealthy &&
        ["youtube", "tv"].includes(candidate?.dataset.heroMediaKind) &&
        livePilotEligible(candidate, rotationProfile)
      ) {
        // Retain the outgoing useful scene while this broadcast starts. One
        // pending stream only; normal cleanup also cancels it on holds/navigation.
        if (pendingLive) return;
        clearRotationTimer();
        clearFallbackTimer();
        if (livePilot && liveStreamLimit() < 2) {
          livePilot.dispose();
          livePilot = null;
        }
        const pending = { handle: null };
        pendingLive = pending;
        pending.handle = mountKioskLive(candidate, {
          offscreen: true,
          onReady: () => {
            if (pendingLive !== pending) return;
            pendingLive = null;
            if (
              disposed ||
              document.hidden ||
              continuity.active ||
              isManualHoldActive() ||
              isSceneSuppressed(candidate)
            ) {
              pending.handle.dispose();
              if (
                !disposed &&
                !document.hidden &&
                !continuity.active &&
                !isManualHoldActive()
              )
                advanceRotation();
              return;
            }
            previousIndex = currentIndex;
            currentIndex = nextIndex;
            render(pending.handle);
          },
          onUnavailable: () => {
            // play() can fail synchronously, before the handle is assigned.
            window.setTimeout(() => {
              if (pendingLive === pending) {
                pendingLive = null;
                pending.handle.dispose();
                advanceRotation();
              } else if (!disposed && livePilot === pending.handle) {
                // A formerly playing broadcast stalled: move on, not back to
                // another long connecting screen. The player sets its cooldown.
                livePilot.dispose();
                livePilot = null;
                advanceRotation();
              }
            }, 0);
          },
        });
        return;
      }
      previousIndex = currentIndex;
      currentIndex = nextIndex;
      refreshQueue();
      render();
    };

    const rotate = () => {
      if (
        pendingLive ||
        document.hidden ||
        scenes.length < 2 ||
        continuity.active ||
        disposed ||
        (isManualHoldActive() && priorityResumeIndex < 0)
      )
        return;
      if (reloadForAssets()) return;
      // Count completed ordinary viewing, not alert interruptions or manual holds.
      if (priorityResumeIndex < 0 && !isSceneSuppressed(scenes[currentIndex])) {
        rotationBalance?.viewed(scenes[currentIndex]);
        refreshQueue();
      }
      if (priorityResumeIndex < 0 && overviewsEnabled && ++normalViews >= 2) {
        normalViews = 0;
        const selection = withOfficeTelevision(
          chooseOverview(
            scenes,
            overviewCatalogs,
            isSceneSuppressed,
            overviewIndex,
            rotationProfile,
            (name) => rotationBalance?.recentlyViewed(name) || false,
          ),
          scenes,
          isSceneSuppressed,
          overviewIndex,
          rotationProfile,
        );
        const highlight =
          overviewIndex % 4 === 3 && !selection?.storeVisit
            ? chooseHighlight(
                overviewCatalogs,
                rotationStorage,
                rotationProfile,
              )
            : null;
        if (selection || highlight) {
          overviewIndex = (overviewIndex + 1) % 1000000;
          try {
            window.localStorage.setItem(
              overviewIndexStorage,
              String(overviewIndex),
            );
          } catch {
            // Session-only sequencing remains available.
          }
          clearFallbackTimer();
          stopTimelapse();
          const mountOverview = highlight
            ? (item, host, ready, finish) =>
                createHighlight(item, host, ready, finish, rotationStorage)
            : createOverview;
          overview = mountOverview(
            highlight || selection,
            stageShell,
            () => {
              scenes.forEach((scene) => syncSceneVideo(scene, false));
            },
            (relatedNames) => {
              overview = null;
              if (!highlight)
                rememberOverviewViews(rotationBalance, scenes, relatedNames);
              // A completed four-up already covered these cameras. Let the
              // refreshed fairness queue choose the next view instead of
              // immediately showing one of the same tiles full-screen again.
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
      disposeOverview();
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
            : targetIndex === currentIndex && !isManualHoldActive()
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
          isManualHoldActive() ? "Return to held view" : "Resume rotation",
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
      const candidate = updateLandingAvailability(
        scenes,
        currentIndex,
        available,
        rotationProfile,
        isSceneSuppressed,
      );
      if (candidate === null) return;
      if (manualHold && !manualHold.overview) {
        const heldScene = scenes.find(
          (scene) =>
            scene.dataset.heroName === manualHold.heroName ||
            scene.dataset.sceneId === manualHold.sceneId,
        );
        // A server-confirmed failed feed must not turn a manual hold into a
        // hold on an unrelated fallback or restore that failed feed on reload.
        if (!heldScene || heldScene.dataset.landingFeedUnavailable === "true")
          clearManualHold();
      }
      refreshQueue();
      // Never fall back to cycling through the same rejected cameras.
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
        eventRequest
      ) {
        return;
      }

      const controller =
        typeof AbortController === "function" ? new AbortController() : null;
      let rejectTimeout;
      const timeout = new Promise((_, reject) => {
        rejectTimeout = reject;
      });
      const requestTimer = window.setTimeout(() => {
        controller?.abort();
        // An aborted fetch or response.json() may never settle on a kiosk.
        // Release the poll slot so the next interval can try again.
        rejectTimeout(new Error("Metadata request timed out"));
      }, 4000);
      const request = {
        cancel() {
          window.clearTimeout(requestTimer);
          controller?.abort();
          rejectTimeout(new Error("Metadata request cancelled"));
        },
      };
      eventRequest = request;
      try {
        const separator = eventsUrl.includes("?") ? "&" : "?";
        const payload = await Promise.race([
          window
            .fetch(`${eventsUrl}${separator}_ts=${Date.now()}`, {
              cache: "no-store",
              signal: controller?.signal,
              credentials: "same-origin",
              headers: { Accept: "application/json" },
            })
            .then((response) => {
              if (!response.ok) throw new Error("Feed request failed");
              return response.json();
            }),
          timeout,
        ]);
        if (disposed || eventRequest !== request || document.hidden) return;
        if (!payload || !Array.isArray(payload.events))
          throw new Error("Invalid feed response");
        const assetRevision = payload.asset_revision;
        if (
          pageAssetRevision &&
          typeof assetRevision === "string" &&
          assetRevision &&
          assetRevision !== pageAssetRevision
        ) {
          if (assetRevision === assetRevisionCandidate)
            pendingAssetReload = true;
          else {
            assetRevisionCandidate = assetRevision;
            pendingAssetReload = false;
          }
        } else {
          assetRevisionCandidate = "";
          pendingAssetReload = false;
        }
        pendingCatalogReload = catalogChanged(payload.available_cameras);
        metadataHealthy = true;
        delete stageShell.dataset.landingMetadataStale;
        syncAvailableCameras(payload?.available_cameras);
        applyLandingCaptionUpdates(scenes, payload?.caption_updates);

        if (
          overview?.cameras.some((camera) => isSceneSuppressed(camera.scene))
        ) {
          disposeOverview();
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
          if ((timelapseDue || !livePilot || continuity.active) && !overview)
            evaluateCurrentScene(currentIndex);
          return;
        }
        activateEvent(eventData);
      } catch {
        if (!disposed && eventRequest === request) {
          assetRevisionCandidate = "";
          pendingAssetReload = false;
          pendingCatalogReload = catalogChanged(null);
          metadataHealthy = false;
          stageShell.dataset.landingMetadataStale = "true";
          // If canvas storage is unavailable, preserve already-loaded scenes.
          if (continuity.available)
            holdRotation("Server unavailable. Retrying automatically…");
        }
      } finally {
        window.clearTimeout(requestTimer);
        if (eventRequest === request) eventRequest = null;
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
      image.addEventListener("landing-image-failed", () => {
        // A background refresh can fail while the displayed frame is valid.
        // Keep its original capture timestamp until a replacement really loads.
        if (!image.complete || !image.naturalWidth)
          advanceFromWeakScene(sceneIndex);
      });
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
    progressTimer = window.setInterval(
      checkRotationProgress,
      LANDING_PROGRESS_CHECK_MS,
    );
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
        cancelEventRequest();
        cancelTimelapsePreload();
        stopTimelapse();
        disposeOverview();
        clearRotationTimer();
        scenes.forEach((scene) => syncSceneVideo(scene, false));
        return;
      }
      clearRotationTimer();
      pollLandingEvents();
      if (continuity.active || isManualHoldActive()) {
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
      // Hiding disposes live/replay playback. Re-evaluate the accepted still
      // on return so a single-scene kiosk need not wait for another rotation.
      evaluateCurrentScene(currentIndex);
    };
    document.addEventListener("visibilitychange", handleVisibilityChange);
    const handleOffline = () => {
      cancelEventRequest();
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
        cancelEventRequest();
        cancelTimelapsePreload();
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
        disposeOverview();
        overviewDisposed = true;
        window.clearTimeout(overviewRefreshTimer);
        overviewController?.abort();
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
        if (progressTimer) {
          window.clearInterval(progressTimer);
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
