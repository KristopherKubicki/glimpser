import { showSpinner, hideSpinner, showErrorIndicator } from "./video.js";

function safePlay(el) {
  const p = el.play?.();
  if (p && typeof p.catch === "function") p.catch(() => {});
}

function sendClientBeacon(event, data) {
  if (window.__GLIMPSER_DISABLE_BEACONS) return;
  try {
    fetch("/client_beacon", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      keepalive: true,
      body: JSON.stringify({
        event,
        path: window.location?.pathname || "",
        data,
      }),
    }).catch(() => {});
  } catch (_) {
    // ignore
  }
}

if (!window.__glimpserErrorBeaconInstalled) {
  window.__glimpserErrorBeaconInstalled = true;
  window.addEventListener("error", (e) => {
    try {
      sendClientBeacon("client_error", {
        message: String(e?.message || ""),
        filename: String(e?.filename || ""),
        lineno: Number(e?.lineno || 0),
        colno: Number(e?.colno || 0),
      });
    } catch (_) {
      // ignore
    }
  });
  window.addEventListener("unhandledrejection", (e) => {
    try {
      sendClientBeacon("client_rejection", {
        reason: String(e?.reason || ""),
      });
    } catch (_) {
      // ignore
    }
  });
}

export function adjustFullHeight() {
  const container = document.querySelector(".video-container.full-height");
  if (!container) return;
  const header = document.querySelector("header");
  const banner = document.getElementById("network-banner");
  const footerSpace = parseFloat(
    getComputedStyle(document.documentElement).getPropertyValue(
      "--footer-space",
    ) || "0",
  );
  const headerHeight = header ? header.offsetHeight : 0;
  const bannerHeight = banner ? banner.offsetHeight : 0;
  document.documentElement.style.setProperty(
    "--header-space",
    `${headerHeight}px`,
  );
  document.documentElement.style.setProperty(
    "--banner-space",
    `${bannerHeight}px`,
  );
  const available =
    window.innerHeight - headerHeight - bannerHeight - footerSpace;
  container.style.maxHeight = `${available}px`;
  if (window.innerWidth >= 768) {
    container.style.height = `${available}px`;
  } else {
    container.style.height = "auto";
  }
}

export function initTilePlayer() {
  const video = document.getElementById("live-video");
  if (!video) return;
  video.addEventListener("contextmenu", (e) => e.preventDefault());
  const source = video.querySelector("source");
  const hasClipSource = Boolean(source && source.src);
  const camSelect =
    document.getElementById("camera-selector") ||
    document.getElementById("nav-camera-dropdown");
  const isLivePage = window.location?.pathname === "/live";

  // Ensure the synthetic "All" group exists so playback can default
  // to cycling through every camera when no specific selection is made.
  if (!window.templateDetails["All"]) {
    window.templateDetails["All"] = {
      groupCameras: Object.keys(window.templateDetails || {}),
    };
  }
  const urlParams = new URLSearchParams(window.location.search || "");
  const forceAllRotator = urlParams.get("rotator") === "all";
  let forcedRotatorActive = forceAllRotator;
  const hasExplicitLiveSelection =
    isLivePage &&
    (urlParams.has("camera") || urlParams.has("group") || forceAllRotator);

  // Only inherit nav state on /live when the URL explicitly asked for a camera/group.
  // Otherwise browsers can restore a stale dropdown selection (often Waze) and pin /live.
  const preferredCamera =
    hasExplicitLiveSelection && typeof window.currentCamera === "string"
      ? window.currentCamera
      : "";
  const preferredGroup =
    hasExplicitLiveSelection && typeof window.currentGroup === "string"
      ? window.currentGroup
      : "";

  const realCameras = Object.keys(window.templateDetails || {}).filter(
    (name) => name !== "All",
  );
  const singleCamera = realCameras.length === 1 ? realCameras[0] : "";

  let current = forceAllRotator
    ? "All"
    : preferredCamera && window.templateDetails?.[preferredCamera]
      ? preferredCamera
      : preferredGroup && preferredGroup !== "all"
        ? `group-${preferredGroup}`
        : isLivePage && !hasExplicitLiveSelection
          ? "All"
          : isLivePage && singleCamera
            ? singleCamera
            : camSelect && camSelect.value
              ? camSelect.value
              : "All";

  sendClientBeacon("tile_player_init", {
    forceAllRotator,
    hasExplicitLiveSelection,
    current,
  });

  if (forceAllRotator) {
    window.currentCamera = null;
    window.currentGroup = null;
    if (camSelect) {
      const hasAll = Array.from(camSelect.options || []).some(
        (opt) => opt.value === "All",
      );
      if (hasAll) camSelect.value = "All";
    }
  }

  function syncLiveContext(selection) {
    let camera = null;
    let group = null;
    if (selection && selection !== "All") {
      if (selection.startsWith("group-")) {
        group = selection.slice(6);
      } else {
        camera = selection;
        const navGroup = document.getElementById("nav-group-dropdown");
        if (navGroup?.value && navGroup.value !== "all") {
          group = navGroup.value;
        }
      }
    }
    if (typeof window.setLiveNavContext === "function") {
      window.setLiveNavContext({ camera, group });
    } else {
      window.currentCamera = camera;
      window.currentGroup = group;
    }
  }

  let abortCtl;
  let lastPlayBeaconAt = 0;
  let liveTimer;

  const container = video.parentElement;

  // Smooth camera switching: cross-fade + optional contrast/brightness guard.
  const FLASH_GUARD_ENABLED = localStorage.getItem("flashGuard") !== "0";
  const FLASH_TARGET_LUMA = Math.min(
    0.8,
    Math.max(
      0.2,
      parseFloat(localStorage.getItem("flashTargetLuma") || "0.55"),
    ),
  );
  const FLASH_GUARD_DARK_BIAS =
    window.matchMedia?.("(prefers-color-scheme: dark)")?.matches ?? true;

  let flashShield = container?.querySelector("#flash-shield") || null;
  if (!flashShield && container) {
    flashShield = document.createElement("div");
    flashShield.id = "flash-shield";
    flashShield.className = "flash-shield";
    container.appendChild(flashShield);
  }
  if (flashShield && flashShield.parentElement === container) {
    // Keep the shield directly after the video so UI overlays remain above it.
    video.insertAdjacentElement("afterend", flashShield);
  }

  let _lumaCanvas = null;
  let _lumaCtx = null;
  let _lastLuma = null;
  let _burstUntil = 0;
  let _burstDir = 0; // 1 => new is brighter (darken), -1 => new is darker (lighten)

  function _clamp(min, v, max) {
    return Math.max(min, Math.min(max, v));
  }

  function _ensureLumaCtx() {
    if (_lumaCtx) return _lumaCtx;
    _lumaCanvas = document.createElement("canvas");
    _lumaCanvas.width = 24;
    _lumaCanvas.height = 24;
    _lumaCtx = _lumaCanvas.getContext("2d", { willReadFrequently: true });
    return _lumaCtx;
  }

  function _sampleLuma(el) {
    try {
      const ctx = _ensureLumaCtx();
      if (!ctx || !el) return null;
      const w = _lumaCanvas.width;
      const h = _lumaCanvas.height;
      ctx.drawImage(el, 0, 0, w, h);
      const data = ctx.getImageData(0, 0, w, h).data;
      let sum = 0;
      const n = w * h;
      for (let i = 0; i < data.length; i += 4) {
        // Rec.709 luma approximation
        sum += 0.2126 * data[i] + 0.7152 * data[i + 1] + 0.0722 * data[i + 2];
      }
      return sum / (n * 255);
    } catch (_) {
      // Cross-origin/canvas taint or draw failure.
      return null;
    }
  }

  function _applyFlashGuard(luma) {
    if (!FLASH_GUARD_ENABLED) return;
    if (luma == null) return;

    const now = Date.now();
    const prev = _lastLuma;
    if (prev != null) {
      const delta = Math.abs(luma - prev);
      if (delta > 0.35) {
        _burstUntil = now + 240;
        _burstDir = luma > prev ? 1 : -1;
      }
    }
    _lastLuma = luma;

    // Gentle normalization: keep it subtle so it doesn't look "filtered".
    // Dark-bias: prefer *darkening* bright scenes; avoid aggressively brightening
    // dark scenes (which can feel washed out at night).
    const brightenMax = FLASH_GUARD_DARK_BIAS ? 1.04 : 1.12;
    const darkenMin = 0.78;
    const desired = FLASH_TARGET_LUMA / Math.max(luma, 0.05);
    const scale =
      desired > 1
        ? _clamp(0.95, desired, brightenMax)
        : _clamp(darkenMin, desired, 1.0);
    const contrast = _clamp(0.92, 1.04 - Math.abs(luma - 0.5) * 0.18, 1.05);
    const filter = `brightness(${scale.toFixed(3)}) contrast(${contrast.toFixed(3)})`;

    video.style.filter = filter;
    // The still underneath should match the live feed visually.
    const img = document.getElementById("live-image");
    if (img) img.style.filter = filter;

    if (flashShield) {
      // Add a small adaptive tint to reduce extreme flashes.
      // Bright scenes: darken slightly. Dark scenes: lighten slightly.
      const hi = Math.max(0, luma - 0.7);
      const lo = Math.max(0, 0.3 - luma);
      let a = Math.max(hi, lo) * 1.2;
      let tint = FLASH_GUARD_DARK_BIAS ? "black" : hi >= lo ? "black" : "white";

      // If the scene luma jumps hard, add a brief "cap" so the switch
      // doesn't feel like a flashbang.
      if (now < _burstUntil) {
        const t = 1 - (now - (_burstUntil - 240)) / 240;
        const burstA = 0.18 * _clamp(0, t, 1);
        if (_burstDir === 1) {
          tint = "black";
          a = Math.max(a, burstA);
        } else if (_burstDir === -1) {
          // In dark-bias mode, keep using black to avoid a "washed" look.
          tint = FLASH_GUARD_DARK_BIAS ? "black" : "white";
          a = Math.max(a, burstA);
        }
      }

      a = _clamp(0, a, 0.25);
      if (a <= 0.001) {
        flashShield.style.backgroundColor = "rgba(0,0,0,0)";
      } else {
        flashShield.style.backgroundColor =
          tint === "black"
            ? `rgba(0,0,0,${a.toFixed(3)})`
            : `rgba(255,255,255,${a.toFixed(3)})`;
      }
    }
  }

  function updateFlashGuardFrom(el) {
    if (!FLASH_GUARD_ENABLED) return;
    const luma = _sampleLuma(el);
    _applyFlashGuard(luma);
  }

  let _softImageSeq = 0;
  function setImageSrcSoft(src) {
    if (!src) return;
    const img = document.getElementById("live-image");
    if (!img) return;

    _softImageSeq += 1;
    const seq = _softImageSeq;

    const pre = new Image();
    pre.onload = () => {
      if (seq != _softImageSeq) return;
      img.style.opacity = "0";
      // Switch src on the next frame so opacity transition applies.
      requestAnimationFrame(() => {
        if (seq != _softImageSeq) return;
        img.src = src;
      });
    };
    pre.onerror = () => {
      if (seq != _softImageSeq) return;
      img.src = src;
    };
    pre.src = src;
  }

  function setMediaAspect(width, height) {
    if (!container) return;
    const w = Number(width);
    const h = Number(height);
    if (!Number.isFinite(w) || !Number.isFinite(h) || w <= 0 || h <= 0) {
      container.style.removeProperty("--media-aspect");
      return;
    }
    container.style.setProperty("--media-aspect", `${w} / ${h}`);
  }

  video.addEventListener("loadedmetadata", () => {
    setMediaAspect(video.videoWidth, video.videoHeight);
  });

  let liveClock = container?.querySelector("#live-clock");
  if (!liveClock && container) {
    liveClock = document.createElement("div");
    liveClock.id = "live-clock";
    liveClock.className = "live-clock";
    liveClock.setAttribute("aria-hidden", "true");
    container.appendChild(liveClock);
  }

  let liveSourceBadge = container?.querySelector("#live-source-badge");
  if (!liveSourceBadge && container) {
    liveSourceBadge = document.createElement("div");
    liveSourceBadge.id = "live-source-badge";
    liveSourceBadge.className = "live-source-badge";
    liveSourceBadge.setAttribute("aria-hidden", "true");
    liveSourceBadge.style.display = "none";
    container.appendChild(liveSourceBadge);
  }

  function setLiveSourceBadge(text, state = "ok") {
    if (!liveSourceBadge) return;
    if (!text) {
      liveSourceBadge.style.display = "none";
      liveSourceBadge.textContent = "";
      liveSourceBadge.dataset.state = "";
      return;
    }
    liveSourceBadge.textContent = text;
    liveSourceBadge.dataset.state = state;
    liveSourceBadge.style.display = "block";
  }

  const timeFmt = new Intl.DateTimeFormat(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
  const updateClock = () => {
    if (!liveClock) return;
    liveClock.textContent = `Live ${timeFmt.format(new Date())}`;
  };
  updateClock();
  setInterval(updateClock, 1000);

  let spinner = container?.querySelector(".loading-spinner");
  if (!spinner && container) {
    spinner = document.createElement("div");
    spinner.className = "loading-spinner";
    spinner.setAttribute("aria-hidden", "true");
    container.appendChild(spinner);
  }

  const liveQualitySelect = document.getElementById("live-quality");
  const liveActionBtn = document.getElementById("live-action");
  const liveStatsEl = document.getElementById("live-stats");
  let liveActionMode = "";
  let liveAutoStage = "first";
  let liveAutoUpgradeTimer = null;
  let liveActionCamera = null;
  let forceLiveCamera = null;
  let liveQuality =
    liveQualitySelect?.value ||
    localStorage.getItem("liveQuality") ||
    (window.LOW_CPU_MODE ? "low" : "auto");
  if (!{ auto: 1, low: 1, high: 1 }[liveQuality]) liveQuality = "auto";
  if (liveQualitySelect) {
    liveQualitySelect.value = liveQuality;
    liveQualitySelect.addEventListener("change", () => {
      liveQuality = liveQualitySelect.value;
      liveAutoStage = "first";
      clearLiveAutoUpgradeTimer();
      localStorage.setItem("liveQuality", liveQuality);
      // Restart the live stream immediately with the new quality.
      if (current && shouldUseLiveVideo(current)) {
        play(current);
      }
    });
  }

  function clearLiveAutoUpgradeTimer() {
    if (liveAutoUpgradeTimer) {
      clearTimeout(liveAutoUpgradeTimer);
      liveAutoUpgradeTimer = null;
    }
  }

  function getEffectiveLiveQuality() {
    if (liveQuality !== "auto") return liveQuality;
    return liveAutoStage;
  }

  function getProfilePlanForQuality(q) {
    return q === "low" || q === "first" ? ["sub", "main"] : ["main", "sub"];
  }

  const WARM_LIVE_DEBOUNCE_MS = 15000;
  const warmSentAt = new Map();

  function maybeWarmCamera(cam) {
    if (!isLivePage) return;
    if (!cam || cam === "All" || String(cam).startsWith("group-")) return;
    if (window.LOW_CPU_MODE) return;
    const det = window.templateDetails?.[cam] || {};
    const kind = det.capabilities?.kind || "";
    if (
      !det.capabilities?.live_video &&
      !["rtsp", "hls", "mjpeg"].includes(kind)
    )
      return;
    const now = Date.now();
    const key = `${cam}::first`;
    const last = warmSentAt.get(key) || 0;
    if (now - last < WARM_LIVE_DEBOUNCE_MS) return;
    warmSentAt.set(key, now);
    fetch(
      `/warm_live?camera=${encodeURIComponent(cam)}&profile=sub&quality=first&t=${now}`,
      { cache: "no-store" },
    ).catch(() => {});
  }

  function maybeWarmCameraHigh(cam) {
    if (!isLivePage) return;
    if (!cam || cam === "All" || String(cam).startsWith("group-")) return;
    if (window.LOW_CPU_MODE) return;
    const det = window.templateDetails?.[cam] || {};
    const kind = det.capabilities?.kind || "";
    if (
      !det.capabilities?.live_video &&
      !["rtsp", "hls", "mjpeg"].includes(kind)
    )
      return;
    const now = Date.now();
    const key = `${cam}::high`;
    const last = warmSentAt.get(key) || 0;
    // High-res warm is more expensive; keep it less chatty.
    if (now - last < 30000) return;
    warmSentAt.set(key, now);
    fetch(
      `/warm_live?camera=${encodeURIComponent(cam)}&profile=main&quality=high&t=${now}`,
      { cache: "no-store" },
    ).catch(() => {});
  }

  function maybeWarmSelection(sel) {
    if (!isLivePage) return;
    if (!sel || sel === "All") return;
    if (String(sel).startsWith("group-")) {
      const group = String(sel).slice(6);
      const cams = camerasForGroup(group).slice(0, 2);
      cams.forEach(maybeWarmCamera);
      return;
    }
    maybeWarmCamera(sel);
  }

  function liveStateKey(camera, suffix) {
    return `live:${suffix}:${camera}`;
  }

  function getLiveBadUntil(camera) {
    if (!camera) return 0;
    const raw = localStorage.getItem(liveStateKey(camera, "badUntil"));
    const n = Number(raw) || 0;
    return Number.isFinite(n) ? n : 0;
  }

  function markLiveBad(camera, ms = 120000) {
    if (!camera) return;
    const until = Date.now() + Math.max(30000, ms);
    localStorage.setItem(liveStateKey(camera, "badUntil"), String(until));
  }

  function clearLiveBad(camera) {
    if (!camera) return;
    localStorage.removeItem(liveStateKey(camera, "badUntil"));
  }

  function getLastGoodProfile(camera) {
    if (!camera) return "";
    return (localStorage.getItem(liveStateKey(camera, "profile")) || "").trim();
  }

  function setLastGoodProfile(camera, profile) {
    if (!camera || !profile) return;
    localStorage.setItem(liveStateKey(camera, "profile"), profile);
  }

  function canAttemptLive(camera) {
    const until = getLiveBadUntil(camera);
    if (until && Date.now() <= until) return false;

    // Respect server-side backoff (persisted in live_caps.json) when provided.
    const det = window.templateDetails?.[camera] || {};
    const avoidForS = Number(det.capabilities?.avoid_for_s || 0) || 0;
    if (avoidForS > 0) return false;
    if (det.capabilities?.auto_live_video === false) return false;

    return true;
  }

  function getLiveCooldownUntil(camera) {
    if (!camera) return 0;
    const raw = localStorage.getItem(liveStateKey(camera, "cooldownUntil"));
    const n = Number(raw) || 0;
    return Number.isFinite(n) ? n : 0;
  }

  function setLiveCooldownUntil(camera, untilMs) {
    if (!camera) return;
    const until = Number(untilMs) || 0;
    if (!until) {
      localStorage.removeItem(liveStateKey(camera, "cooldownUntil"));
      return;
    }
    localStorage.setItem(liveStateKey(camera, "cooldownUntil"), String(until));
  }

  function setLiveAction(mode, camera = null) {
    liveActionMode = mode || "";
    liveActionCamera = camera;
    if (!liveActionBtn) return;

    const q = getEffectiveLiveQuality();
    let visible = false;
    let label = "";
    let title = "";

    if (mode === "upgrade") {
      visible =
        !window.LOW_CPU_MODE &&
        (liveQuality === "low" || liveQuality === "auto") &&
        q !== "high";
      label = "Upgrade";
      title = "Upgrade to higher quality live stream";
    } else if (mode === "try") {
      visible = Boolean(camera) && shouldUseLiveVideo(String(camera));
      label = "Try Live";
      title = "Try RTSP live stream again";
    }

    liveActionBtn.textContent = label;
    liveActionBtn.title = title;
    liveActionBtn.style.display = visible ? "" : "none";
  }

  function updateLiveStats() {
    if (!liveStatsEl) return;
    const w = Number(video.videoWidth) || 0;
    const h = Number(video.videoHeight) || 0;
    if (!w || !h) {
      liveStatsEl.textContent = "";
      return;
    }
    const q = getEffectiveLiveQuality();
    liveStatsEl.textContent = `${w}x${h} (${q})`;
    updateFlashGuardFrom(video);
  }

  if (liveActionBtn) {
    liveActionBtn.addEventListener("click", () => {
      const cam =
        liveActionCamera || (typeof current === "string" ? current : null);
      if (!cam) return;

      if (liveActionMode === "try") {
        clearLiveAutoUpgradeTimer();
        clearLiveBad(cam);
        forceLiveCamera = cam;
        play(cam);
        // Clear the override after we kick off the attempt.
        setTimeout(() => {
          if (forceLiveCamera === cam) forceLiveCamera = null;
        }, 0);
        return;
      }

      if (liveActionMode === "upgrade") {
        clearLiveAutoUpgradeTimer();
        if (liveQuality === "auto") {
          liveAutoStage = "high";
          setLiveAction("", cam);
          play(cam);
          return;
        }
        liveQuality = "high";
        if (liveQualitySelect) liveQualitySelect.value = liveQuality;
        localStorage.setItem("liveQuality", liveQuality);
        setLiveAction("", cam);
        play(cam);
      }
    });
  }

  video.addEventListener("loadedmetadata", updateLiveStats);

  const speedSlider = document.getElementById("speed-slider");
  const speedValue = document.getElementById("speed-value");
  let refreshSeconds = speedSlider
    ? Math.max(1, parseInt(speedSlider.value, 10) || 1)
    : 1;
  let pngTimer = null;
  let switchSeq = 0;
  let refreshAbort = null;
  let refreshTimeoutIds = [];
  const lastAdhocRefresh = new Map();
  let spinnerMinUntil = 0;
  let clipSeq = 0;
  let clipLoopsRemaining = 0;
  let clipFailTimer = null;
  let clipControls = null;
  let clipSeek = null;
  let clipTime = null;
  let clipIsSeeking = false;
  let clipSeekRaf = null;
  let clipTargetTime = null;
  let liveVideoCleanup = null;
  let liveProfileRetryTimer = null;
  let liveConnectTimer = null;
  let streamRecoverTimer = null;
  let streamRecoverDelayMs = 1200;
  let backendCheckTimer = null;
  let backendWasDown = false;
  let backendConsecutiveFails = 0;
  let rotationTimer = null;
  let rotationRoot = null;
  let rotationIndex = -1;

  const STREAM_RECOVER_MAX_DELAY_MS = 12000;
  const ROTATION_DWELL_MS = 6000;
  const BACKEND_HEALTH_POLL_MS = 4000;
  const LIVE_FADE_MS = 1800;
  const speedContainer = document.getElementById("speed-container");

  function setSpeedControlsVisible(visible) {
    if (!speedContainer) return;
    speedContainer.style.display = visible ? "" : "none";
  }

  function prefersReducedMotion() {
    return window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches;
  }

  function crossFadeToVideo(token) {
    if (!isLivePage) return;
    if (!video || !image) return;
    if (token != null && image.dataset.streamToken !== String(token)) return;

    const ms = prefersReducedMotion() ? 0 : LIVE_FADE_MS;
    video.style.transitionDuration = `${ms}ms`;
    image.style.transitionDuration = `${ms}ms`;

    // Keep the last frame visible while the new stream fades in.
    video.style.display = "block";
    // Ensure the image is visible for the fade out, but don't force it if it
    // wasn't (previews can be disabled in some flows).
    if (image.style.display === "none") image.style.display = "block";

    video.style.opacity = "0";
    image.style.opacity = image.style.opacity || "1";

    requestAnimationFrame(() => {
      if (token != null && image.dataset.streamToken !== String(token)) return;
      video.style.opacity = "1";
      image.style.opacity = "0";
      setTimeout(() => {
        if (token != null && image.dataset.streamToken !== String(token))
          return;
        image.style.display = "none";
        image.style.opacity = "1";
      }, ms + 80);
    });
  }

  function captureVideoFrameToStill() {
    if (!isLivePage) return false;
    if (!video || !image) return false;
    if (video.style.display === "none") return false;
    const w = video.videoWidth || 0;
    const h = video.videoHeight || 0;
    if (!w || !h) return false;

    try {
      const canvas = document.createElement("canvas");
      canvas.width = w;
      canvas.height = h;
      const ctx = canvas.getContext("2d", { alpha: false });
      if (!ctx) return false;
      ctx.drawImage(video, 0, 0, w, h);
      // JPEG is widely supported and fast enough for a single transition frame.
      const dataUrl = canvas.toDataURL("image/jpeg", 0.65);
      if (!dataUrl) return false;

      image.dataset.mode = "preview";
      image.src = dataUrl;
      image.style.display = "block";
      image.style.opacity = "1";
      return true;
    } catch (_) {
      return false;
    }
  }

  function primeTransitionStill() {
    if (!isLivePage) return;
    if (!image) return;

    // If we already have a visible still, keep it.
    const hasStill =
      image.style.display !== "none" && Boolean(image.getAttribute("src"));
    if (hasStill) return;

    // Otherwise, try to snapshot the current video so we always have something
    // to fade from (rotation / rapid switching can skip last_screenshot preload).
    captureVideoFrameToStill();
  }

  function crossFadeToImage() {
    if (!isLivePage) return;
    if (!video || !image) return;
    const ms = prefersReducedMotion() ? 0 : LIVE_FADE_MS;
    video.style.transitionDuration = `${ms}ms`;
    image.style.transitionDuration = `${ms}ms`;

    image.style.display = "block";
    image.style.opacity = "0";
    requestAnimationFrame(() => {
      image.style.opacity = "1";
      video.style.opacity = "0";
      setTimeout(() => {
        video.style.display = "none";
        video.style.opacity = "1";
      }, ms + 80);
    });
  }

  function updateSpeedLabel() {
    if (!speedValue || !speedSlider) return;
    const secs = Math.max(1, parseInt(speedSlider.value, 10) || 1);
    refreshSeconds = secs;
    speedValue.textContent =
      secs === 60 ? "1fpm" : `${(1 / secs).toFixed(2)}fps`;
  }

  function resetStreamRecovery() {
    if (streamRecoverTimer) {
      clearTimeout(streamRecoverTimer);
      streamRecoverTimer = null;
    }
    streamRecoverDelayMs = 1200;
  }

  function isLiveStreamActive() {
    if (!isLivePage || hasClipSource) return false;
    if (image?.dataset?.mode === "stream") return true;
    if (liveVideoCleanup && video.style.display !== "none") return true;
    return false;
  }

  function scheduleStreamRecovery(reason = "reconnect", minDelayMs = 0) {
    if (!isLiveStreamActive()) return;
    if (streamRecoverTimer) return;

    const delay = Math.max(minDelayMs, streamRecoverDelayMs);
    streamRecoverTimer = setTimeout(() => {
      streamRecoverTimer = null;
      if (!isLiveStreamActive()) return;
      if (backendWasDown) {
        setLiveSourceBadge("Reconnecting to backend...", "probing");
      }
      showSpinner(video);
      play(current);
      streamRecoverDelayMs = Math.min(
        STREAM_RECOVER_MAX_DELAY_MS,
        Math.round(streamRecoverDelayMs * 1.8),
      );
    }, delay);

    if (reason && isLivePage) {
      console.debug(
        `[live] scheduling stream recovery (${reason}) in ${delay}ms`,
      );
    }
  }

  async function checkBackendHealthForLive() {
    if (!isLiveStreamActive()) return;
    try {
      const res = await fetch("/health", {
        cache: "no-store",
        headers: { Accept: "application/json" },
      });
      if (!res.ok) throw new Error(`health ${res.status}`);
      backendConsecutiveFails = 0;
      if (backendWasDown) {
        backendWasDown = false;
        resetStreamRecovery();
        scheduleStreamRecovery("backend-up", 120);
      }
    } catch (_) {
      backendConsecutiveFails += 1;
      if (backendConsecutiveFails >= 2) {
        backendWasDown = true;
      }
      if (backendWasDown) {
        scheduleStreamRecovery("backend-down", 1200);
      }
    }
  }

  if (speedSlider) speedSlider.addEventListener("input", updateSpeedLabel);
  updateSpeedLabel();

  let image = document.getElementById("live-image");
  if (!image) {
    image = document.createElement("img");
    image.id = "live-image";
    image.style.display = "none";
    if (container) container.appendChild(image);
  }

  image.dataset.mode = image.dataset.mode || "preview";
  let activeStreamToken = 0;
  if (isLivePage && !hasClipSource) {
    backendCheckTimer = setInterval(
      checkBackendHealthForLive,
      BACKEND_HEALTH_POLL_MS,
    );
    setTimeout(checkBackendHealthForLive, 1500);
  }
  image.addEventListener("load", () => {
    setMediaAspect(image.naturalWidth, image.naturalHeight);
    // Only hide the spinner for the most recent stream load. Older in-flight
    // requests can complete out of order during rapid switching.
    if (
      image.dataset.mode === "stream" &&
      image.dataset.streamToken === String(activeStreamToken)
    ) {
      const remaining = spinnerMinUntil - Date.now();
      if (remaining > 0) {
        setTimeout(() => hideSpinner(video), remaining);
      } else {
        hideSpinner(video);
      }
    }
    image.style.opacity = "1";
    backendWasDown = false;
    backendConsecutiveFails = 0;
    resetStreamRecovery();
    updateFlashGuardFrom(image);
  });
  image.addEventListener("error", () => {
    if (
      image.dataset.mode !== "stream" ||
      image.dataset.streamToken !== String(activeStreamToken)
    ) {
      return;
    }
    hideSpinner(video);
    showErrorIndicator(video);
    scheduleStreamRecovery("image-error", 900);
  });

  const fsButton = document.getElementById("fullscreen-toggle");
  if (fsButton) {
    const controlsList = video.controlsList;
    const supportsNoFullscreen = Boolean(
      controlsList &&
        typeof controlsList.supports === "function" &&
        controlsList.supports("nofullscreen"),
    );
    // Keep exactly one fullscreen affordance: either native controls OR our
    // custom overlay button depending on browser capability.
    if (supportsNoFullscreen) {
      video.setAttribute("controlsList", "nofullscreen");
      fsButton.style.display = "block";
    } else {
      fsButton.style.display = "none";
    }
    fsButton.addEventListener("click", () => {
      const target = container || video;
      if (!document.fullscreenElement) {
        target?.requestFullscreen?.();
      } else {
        document.exitFullscreen?.();
      }
    });
  }

  function showBounce() {
    if (!spinner) return;
    spinner.textContent = "\u25CF";
    spinner.classList.add("bouncy", "visible");
  }

  function hideBounce() {
    if (!spinner) return;
    spinner.classList.remove("bouncy", "visible");
  }

  const LIVE_CLASS = "live-mode";
  const IDLE_DELAY = 30000;
  const CLIP_DURATION_SEC = 120;
  const CLIP_LOOP_COUNT = 3;
  const LIVE_CONNECT_TIMEOUT_MS = 5000;
  const LIVE_PROFILE_RECOVERY_MS = 45000;

  function showClip() {
    if (pngTimer) {
      clearInterval(pngTimer);
      pngTimer = null;
    }
    image.style.display = "none";
    video.style.display = "none";
    container?.classList.remove(LIVE_CLASS);
    safePlay(video);
  }

  function showLive() {
    if (clipFailTimer) {
      clearTimeout(clipFailTimer);
      clipFailTimer = null;
    }
    play(current);
  }

  function formatClock(seconds) {
    const s = Math.max(0, Number(seconds) || 0);
    const hh = Math.floor(s / 3600);
    const mm = Math.floor((s % 3600) / 60);
    const ss = Math.floor(s % 60);
    const pad = (n) => String(n).padStart(2, "0");
    return hh > 0 ? `${hh}:${pad(mm)}:${pad(ss)}` : `${mm}:${pad(ss)}`;
  }

  function ensureClipControls() {
    if (!container) return;
    if (clipControls) return;
    clipControls = document.createElement("div");
    clipControls.className = "clip-controls";
    clipControls.setAttribute("aria-hidden", "true");

    clipSeek = document.createElement("input");
    clipSeek.type = "range";
    clipSeek.className = "clip-seek";
    clipSeek.min = "0";
    clipSeek.max = "0";
    clipSeek.step = "0.05";
    clipSeek.value = "0";
    clipSeek.setAttribute("aria-label", "Scrub timeline");

    clipTime = document.createElement("div");
    clipTime.className = "clip-time";
    clipTime.textContent = "0:00";

    clipControls.appendChild(clipSeek);
    clipControls.appendChild(clipTime);
    container.appendChild(clipControls);

    const applySeekTarget = () => {
      clipSeekRaf = null;
      if (clipTargetTime == null) return;
      const t = clipTargetTime;
      clipTargetTime = null;
      try {
        if (typeof video.fastSeek === "function") {
          video.fastSeek(t);
        } else {
          video.currentTime = t;
        }
      } catch (_) {
        // Ignore out-of-range/unsupported seek attempts.
      }
    };

    const queueSeek = (t) => {
      clipTargetTime = t;
      if (clipSeekRaf != null) return;
      clipSeekRaf = requestAnimationFrame(applySeekTarget);
    };

    const startSeek = () => {
      clipIsSeeking = true;
      video.pause();
    };

    const stopSeek = () => {
      if (!clipIsSeeking) return;
      clipIsSeeking = false;
      safePlay(video);
    };

    clipSeek.addEventListener("pointerdown", startSeek);
    clipSeek.addEventListener("pointerup", stopSeek);
    clipSeek.addEventListener("pointercancel", stopSeek);
    clipSeek.addEventListener("touchstart", startSeek, { passive: true });
    clipSeek.addEventListener("touchend", stopSeek);

    clipSeek.addEventListener("input", () => {
      const t = Number(clipSeek.value) || 0;
      clipTime.textContent = formatClock(t);
      queueSeek(t);
    });
  }

  let goLiveBtn = container?.querySelector(".go-live-btn");
  if (!goLiveBtn && container) {
    goLiveBtn = document.createElement("button");
    goLiveBtn.type = "button";
    goLiveBtn.className = "go-live-btn";
    goLiveBtn.textContent = "Live";
    goLiveBtn.title = "Switch to live stream";
    goLiveBtn.addEventListener("click", () => showLive());
    container.appendChild(goLiveBtn);
  }

  function setClipUiActive(active) {
    if (goLiveBtn) goLiveBtn.style.display = active ? "block" : "none";
    // Speed slider is for live stream refresh rate, not clip playback.
    const wrapper = document.getElementById("controls-wrapper");
    if (wrapper) wrapper.style.display = active ? "none" : "";
    if (isLivePage) {
      // Avoid double scrub bars on /live: use custom clip controls only
      // while playing archived clips.
      video.controls = !active;
      ensureClipControls();
      if (clipControls) clipControls.style.display = active ? "flex" : "none";
    }
  }

  function setVideoSrc(url) {
    // Use the <video> element directly; live.html's <source> has no src.
    // Fade down before switching to avoid hard flashes between scenes.
    video.style.opacity = "0";
    // Apply a neutral guard during connect; it'll be refined once frames arrive.
    if (FLASH_GUARD_ENABLED) {
      video.style.filter = "brightness(0.95) contrast(0.98)";
      const img = document.getElementById("live-image");
      if (img) img.style.filter = "brightness(0.95) contrast(0.98)";
      if (flashShield) flashShield.style.backgroundColor = "rgba(0,0,0,0.10)";
      _burstUntil = Date.now() + 240;
      _burstDir = 1;
    }
    video.removeAttribute("src");
    if (source) source.removeAttribute("src");
    video.src = url;
  }

  function enterClipModeForSelection(name, seq) {
    if (!isLivePage) return false;
    if (!name || name === "All") return false;

    clipSeq += 1;
    const myClipSeq = clipSeq;
    clipLoopsRemaining = CLIP_LOOP_COUNT - 1;

    setClipUiActive(true);
    // Better scrubbing behavior: the clip is the thing you interact with.
    // Live mode uses an <img> element and shouldn't preload.
    video.preload = "auto";
    showSpinner(video);
    spinnerMinUntil = Date.now() + 1000;

    let clipUrl = "";
    let fallbackCamera = null;

    if (name.startsWith("group-")) {
      const group = name.slice(6);
      clipUrl = `/last_teaser?group=${encodeURIComponent(group)}&t=${Date.now()}`;
      const cams = camerasForGroup(group);
      fallbackCamera = cams.length ? cams[0] : null;
    } else {
      clipUrl = `/clip/${encodeURIComponent(name)}?duration=${CLIP_DURATION_SEC}&t=${Date.now()}`;
    }

    const onEnded = () => {
      if (seq !== switchSeq || myClipSeq !== clipSeq) return;
      if (clipLoopsRemaining > 0) {
        clipLoopsRemaining -= 1;
        video.currentTime = 0;
        safePlay(video);
        return;
      }
      showLive();
    };

    const onError = () => {
      if (seq !== switchSeq || myClipSeq !== clipSeq) return;
      if (fallbackCamera) {
        const cam = fallbackCamera;
        fallbackCamera = null;
        clipLoopsRemaining = CLIP_LOOP_COUNT - 1;
        setVideoSrc(
          `/clip/${encodeURIComponent(cam)}?duration=${CLIP_DURATION_SEC}&t=${Date.now()}`,
        );
        video.load();
        safePlay(video);
        return;
      }
      showLive();
    };

    video.addEventListener("ended", onEnded);
    video.addEventListener("error", onError);
    video.addEventListener("loadedmetadata", () => {
      if (!clipSeek) return;
      clipSeek.max = String(video.duration || 0);
      clipSeek.value = String(video.currentTime || 0);
      if (clipTime) clipTime.textContent = formatClock(video.currentTime || 0);
    });
    video.addEventListener("timeupdate", () => {
      if (!clipSeek || clipIsSeeking) return;
      clipSeek.value = String(video.currentTime || 0);
      if (clipTime) clipTime.textContent = formatClock(video.currentTime || 0);
    });

    // Hard failsafe: if the clip never reaches "canplay", drop to live.
    if (clipFailTimer) clearTimeout(clipFailTimer);
    clipFailTimer = setTimeout(() => {
      if (seq !== switchSeq || myClipSeq !== clipSeq) return;
      showLive();
    }, 8000);

    const onCanPlay = () => {
      if (seq !== switchSeq || myClipSeq !== clipSeq) return;
      if (clipFailTimer) {
        clearTimeout(clipFailTimer);
        clipFailTimer = null;
      }
    };
    video.addEventListener("canplay", onCanPlay, { once: true });

    setVideoSrc(clipUrl);
    video.loop = false;
    video.load();
    showClip();

    // Clean up listeners when a new selection happens.
    const cleanupIfStale = () => {
      if (myClipSeq !== clipSeq) {
        video.removeEventListener("ended", onEnded);
        video.removeEventListener("error", onError);
      }
    };
    setTimeout(cleanupIfStale, 0);

    // Ensure we still return to live if user stops interacting.
    scheduleLive(name);
    return true;
  }

  function stillPreviewUrl(name) {
    if (!name) return null;
    if (name === "All") return `/stream.png?time=${Date.now()}`;
    if (name.startsWith("group-")) {
      const group = name.slice(6);
      return `/stream.png?group=${encodeURIComponent(group)}&time=${Date.now()}`;
    }
    return `/last_screenshot/${encodeURIComponent(name)}?time=${Date.now()}`;
  }

  function preloadStill(url) {
    if (!url) return Promise.resolve(false);
    return new Promise((resolve) => {
      const tmp = new Image();
      tmp.onload = () => resolve(true);
      tmp.onerror = () => resolve(false);
      tmp.src = url;
    });
  }

  async function showStillPreview(name, seq) {
    if (!image) return;
    const url = stillPreviewUrl(name);
    if (!url) return;
    // Don't block switching. If the preview is slow or fails, we still want
    // to move to the stream immediately.
    const ok = await Promise.race([
      preloadStill(url),
      new Promise((resolve) => setTimeout(() => resolve(false), 1400)),
    ]);
    if (!ok) return;
    if (seq !== switchSeq) return;
    // If the stream has already started, don't clobber it with a preview.
    if (image.dataset.mode === "stream") return;
    image.dataset.mode = "preview";
    image.style.display = "block";
    video.style.display = "none";
    image.src = url;
  }

  function camerasForGroup(group) {
    if (!group) return [];
    return Object.entries(window.templateDetails || {})
      .filter(([, det]) => {
        const groups = det?.groups;
        if (!groups) return false;
        return groups
          .split(",")
          .map((s) => s.trim())
          .includes(group);
      })
      .map(([cam]) => cam);
  }

  function stopRotationTimer() {
    if (rotationTimer) {
      clearTimeout(rotationTimer);
      rotationTimer = null;
    }
  }

  function rotationTargetsFor(selection) {
    if (selection === "All") {
      return Object.keys(window.templateDetails || {})
        .filter((name) => name && name !== "All")
        .sort((a, b) => a.localeCompare(b));
    }
    if (selection && selection.startsWith("group-")) {
      const group = selection.slice(6);
      return camerasForGroup(group).sort((a, b) => a.localeCompare(b));
    }
    return [];
  }

  function nextRotatedCamera(selection) {
    const targets = rotationTargetsFor(selection);
    if (!targets.length) return null;

    if (rotationRoot !== selection) {
      rotationRoot = selection;
      rotationIndex = -1;
    }

    rotationIndex = (rotationIndex + 1) % targets.length;
    return targets[rotationIndex];
  }

  function cancelAdhocRefresh() {
    if (refreshAbort) refreshAbort.abort();
    refreshAbort = new AbortController();
    refreshTimeoutIds.forEach((id) => clearTimeout(id));
    refreshTimeoutIds = [];
  }

  function canRefresh(key) {
    const now = Date.now();
    const last = lastAdhocRefresh.get(key) || 0;
    // Avoid overwhelming the capture pipeline when users flip rapidly.
    if (now - last < 4000) return false;
    lastAdhocRefresh.set(key, now);
    return true;
  }

  async function triggerAdhocRefresh(name, seq) {
    // Best-effort: if capture is disabled or the endpoint fails, ignore.
    try {
      if (seq !== switchSeq) return;
      if (!name || name === "All") return;
      if (name.startsWith("group-")) {
        const group = name.slice(6);
        if (!canRefresh(`group:${group}`)) return;
        const cams = camerasForGroup(group).slice(0, 12);
        // Avoid firing off a huge burst; stagger a bit.
        await Promise.allSettled(
          cams.map(
            (cam, idx) =>
              new Promise((resolve) => {
                const id = setTimeout(() => {
                  if (seq !== switchSeq) return resolve();
                  if (!canRefresh(`cam:${cam}`)) return resolve();
                  fetch(`/take_screenshot/${encodeURIComponent(cam)}`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({}),
                    signal: refreshAbort?.signal,
                  })
                    .catch(() => {})
                    .finally(resolve);
                }, idx * 150);
                refreshTimeoutIds.push(id);
              }),
          ),
        );
        return;
      }
      if (!canRefresh(`cam:${name}`)) return;
      fetch(`/take_screenshot/${encodeURIComponent(name)}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
        signal: refreshAbort?.signal,
      }).catch(() => {});
    } catch (_) {
      // ignore
    }
  }

  function setPngSrc(target, isCamera) {
    if (!target) return;
    if (target === "all") return `/stream.png?time=${Date.now()}`;
    const param = isCamera ? "camera" : "group";
    return `/stream.png?${param}=${encodeURIComponent(target)}&time=${Date.now()}`;
  }

  function isLikelyRealtimeStreamCamera(name) {
    if (!name || name === "All" || name.startsWith("group-")) return false;
    const details = window.templateDetails?.[name] || {};
    if (details.capabilities && details.capabilities.live_video === false)
      return false;
    if (details.capabilities && details.capabilities.live_video === true)
      return true;
    const rawUrl = String(details.url || "").trim();
    if (!rawUrl) return false;
    const url = rawUrl.toLowerCase();
    if (url.startsWith("rtsp://") || url.startsWith("rtsps://")) return true;
    if (
      url.includes(".m3u8") ||
      url.includes(".mjpg") ||
      url.includes(".mjpeg")
    ) {
      return true;
    }
    if (url.includes("/isapi/streaming/channels/")) return true;
    if (url.includes("/streaming/channels/")) return true;
    return false;
  }

  function shouldUseLiveVideo(name) {
    return (
      isLivePage &&
      !hasClipSource &&
      name &&
      name !== "All" &&
      !name.startsWith("group-") &&
      isLikelyRealtimeStreamCamera(name) &&
      (name === forceLiveCamera || canAttemptLive(name))
    );
  }

  function stopLiveVideoMode() {
    if (liveVideoCleanup) {
      liveVideoCleanup();
      liveVideoCleanup = null;
    }
    if (liveProfileRetryTimer) {
      clearTimeout(liveProfileRetryTimer);
      liveProfileRetryTimer = null;
    }
    if (liveConnectTimer) {
      clearTimeout(liveConnectTimer);
      liveConnectTimer = null;
    }
    setLiveSourceBadge("");
    setLiveAction("", null);
    clearLiveAutoUpgradeTimer();
    if (liveQuality === "auto") liveAutoStage = "first";
    if (liveStatsEl) liveStatsEl.textContent = "";
    setSpeedControlsVisible(true);
    if (!hasClipSource) {
      video.pause();
      video.removeAttribute("src");
      video.load();
    }
  }

  function playLiveVideo(camera, streamToken = 0) {
    if (!camera) return;
    if (pngTimer) {
      clearInterval(pngTimer);
      pngTimer = null;
    }
    stopLiveVideoMode();

    if (forceLiveCamera === camera) forceLiveCamera = null;

    showSpinner(video);
    image.dataset.mode = "preview";
    image.dataset.streamToken = String(streamToken);
    image.style.opacity = "0";
    // Avoid a blank screen while RTSP spins up: keep a still underneath
    // until the first frame is ready.
    image.style.display = "block";
    setImageSrcSoft(stillPreviewUrl(camera) || image.src);

    setClipUiActive(false);
    setSpeedControlsVisible(false);

    if (container) container.classList.remove(LIVE_CLASS);
    video.style.display = "none";
    video.loop = false;
    video.preload = "none";

    const autoUpgradeEligible =
      liveQuality === "auto" &&
      !window.LOW_CPU_MODE &&
      !String(camera).startsWith("group-") &&
      camera !== "All";

    const getQuality = () => getEffectiveLiveQuality();
    const getPlan = (q) => {
      const plan = getProfilePlanForQuality(q);
      const last = getLastGoodProfile(camera);
      if (last && plan.includes(last)) {
        // Prefer the last known-good profile first.
        return [last, ...plan.filter((p) => p !== last)];
      }
      return plan;
    };

    let profileIndex = 0;
    let failedThisAttempt = false;

    let stallCount = 0;
    let waitingCount = 0;
    let lastFrameCount = 0;
    let samples = 0;
    let monitorTimer = null;

    const resetMonitor = () => {
      stallCount = 0;
      waitingCount = 0;
      lastFrameCount = 0;
      samples = 0;
    };

    const getDroppedRatio = () => {
      if (typeof video.getVideoPlaybackQuality !== "function") return 0;
      const q = video.getVideoPlaybackQuality();
      const dropped = Number(q.droppedVideoFrames) || 0;
      const total = Number(q.totalVideoFrames) || 0;
      return total ? dropped / total : 0;
    };

    const getApproxFps = () => {
      if (typeof video.getVideoPlaybackQuality !== "function") return 0;
      const q = video.getVideoPlaybackQuality();
      const total = Number(q.totalVideoFrames) || 0;
      const d = total - lastFrameCount;
      lastFrameCount = total;
      // sample period ~2s
      return (d * 1000) / 2000;
    };

    const maybeDowngradeFromHigh = () => {
      const now = Date.now();
      if (liveQuality !== "auto") return false;
      if (liveAutoStage !== "high") return false;
      if (now < getLiveCooldownUntil(camera)) return false;

      const dropped = getDroppedRatio();
      const fps = getApproxFps();
      const tooManyStalls = stallCount >= 2 || waitingCount >= 2;
      const tooManyDrops = dropped > 0.25;
      const tooLowFps = fps && fps < 6;

      samples += 1;
      // Require a couple samples before taking action.
      if (samples < 2) return false;

      if (tooManyStalls || tooManyDrops || tooLowFps) {
        liveAutoStage = "low";
        setLiveCooldownUntil(camera, now + 60000);
        profileIndex = 0;
        resetMonitor();
        showSpinner(video);
        startAttempt();
        return true;
      }

      return false;
    };

    const startMonitor = () => {
      if (monitorTimer) clearInterval(monitorTimer);
      resetMonitor();
      monitorTimer = setInterval(() => {
        if (streamToken !== activeStreamToken) return;
        // Only adapt when we're in high.
        if (maybeDowngradeFromHigh()) return;
        updateLiveStats();
      }, 2000);
    };

    const stopMonitor = () => {
      if (!monitorTimer) return;
      clearInterval(monitorTimer);
      monitorTimer = null;
    };

    const onWaiting = () => {
      if (streamToken !== activeStreamToken) return;
      waitingCount += 1;
      stallCount += 1;
    };

    const onStalled = () => {
      if (streamToken !== activeStreamToken) return;
      stallCount += 1;
      const q = getQuality();
      setLiveSourceBadge(`Live RTSP (buffering, ${q})`, "probing");
    };

    const startAttempt = () => {
      if (streamToken !== activeStreamToken) return;
      failedThisAttempt = false;

      const q = getQuality();
      const profilePlan = getPlan(q);
      const profile = profilePlan[profileIndex] || "main";

      clearLiveAutoUpgradeTimer();
      setLiveAction(q === "low" || q === "first" ? "upgrade" : "", camera);
      setLiveSourceBadge(`Live RTSP (${profile}, ${q})`, "probing");
      setVideoSrc(
        `/live_video?camera=${encodeURIComponent(camera)}&profile=${profile}&quality=${encodeURIComponent(q)}&time=${Date.now()}`,
      );
      video.load();
      safePlay(video);
      if (liveConnectTimer) clearTimeout(liveConnectTimer);
      liveConnectTimer = setTimeout(() => {
        if (streamToken !== activeStreamToken || failedThisAttempt) return;
        onAttemptFailure("timeout");
      }, LIVE_CONNECT_TIMEOUT_MS);
    };

    const scheduleMainRecovery = () => {
      if (profileIndex === 0) return;
      if (liveProfileRetryTimer) clearTimeout(liveProfileRetryTimer);
      liveProfileRetryTimer = setTimeout(() => {
        if (streamToken !== activeStreamToken) return;
        profileIndex = 0;
        showSpinner(video);
        startAttempt();
      }, LIVE_PROFILE_RECOVERY_MS);
    };

    const onAttemptFailure = () => {
      if (streamToken !== activeStreamToken || failedThisAttempt) return;
      failedThisAttempt = true;
      if (liveConnectTimer) {
        clearTimeout(liveConnectTimer);
        liveConnectTimer = null;
      }

      const q = getQuality();
      const profilePlan = getPlan(q);

      if (profileIndex + 1 < profilePlan.length) {
        profileIndex += 1;
        startAttempt();
        return;
      }

      // Auto mode: if the upgrade stage fails, step back down to low.
      if (liveQuality === "auto" && liveAutoStage === "high") {
        liveAutoStage = "low";
        profileIndex = 0;
        setLiveCooldownUntil(camera, Date.now() + 60000);
        showSpinner(video);
        startAttempt();
        return;
      }

      stopMonitor();
      stopLiveVideoMode();
      markLiveBad(camera, 120000);
      setLiveAction("try", camera);
      playMjpg(camera, true, streamToken);
    };

    const onReady = () => {
      if (streamToken !== activeStreamToken) return;
      if (liveConnectTimer) {
        clearTimeout(liveConnectTimer);
        liveConnectTimer = null;
      }
      const q = getQuality();
      const profilePlan = getPlan(q);
      const profile = profilePlan[profileIndex] || "main";
      setLiveSourceBadge(`Live RTSP (${profile}, ${q})`, "ok");
      hideSpinner(video);
      crossFadeToVideo(streamToken);
      backendWasDown = false;
      backendConsecutiveFails = 0;
      resetStreamRecovery();
      updateFlashGuardFrom(video);
      updateLiveStats();
      clearLiveBad(camera);
      setLastGoodProfile(camera, profile);
      startMonitor();
      scheduleMainRecovery();

      if (liveQuality === "auto") {
        const cooldown = getLiveCooldownUntil(camera);
        setLiveAction(q === "low" || q === "first" ? "upgrade" : "", camera);
        if (autoUpgradeEligible && (!cooldown || Date.now() > cooldown)) {
          if (q === "first") {
            // Fastest possible first frame, then step up.
            liveAutoUpgradeTimer = setTimeout(() => {
              if (streamToken !== activeStreamToken) return;
              if (current !== camera) return;
              if (liveQuality !== "auto") return;
              liveAutoStage = "low";
              profileIndex = 0;
              resetMonitor();
              showSpinner(video);
              startAttempt();
            }, 600);
          } else if (q === "low") {
            maybeWarmCameraHigh(camera);
            liveAutoUpgradeTimer = setTimeout(() => {
              if (streamToken !== activeStreamToken) return;
              if (current !== camera) return;
              if (liveQuality !== "auto") return;
              const cd = getLiveCooldownUntil(camera);
              if (cd && Date.now() < cd) return;
              liveAutoStage = "high";
              profileIndex = 0;
              resetMonitor();
              showSpinner(video);
              startAttempt();
            }, 2000);
          }
        }
      }
    };

    const onError = () => {
      onAttemptFailure();
    };

    video.addEventListener("canplay", onReady);
    video.addEventListener("loadedmetadata", onReady);
    video.addEventListener("loadeddata", onReady);
    video.addEventListener("playing", onReady);
    video.addEventListener("error", onError);
    video.addEventListener("waiting", onWaiting);
    video.addEventListener("stalled", onStalled);
    liveVideoCleanup = () => {
      stopMonitor();
      video.removeEventListener("canplay", onReady);
      video.removeEventListener("loadedmetadata", onReady);
      video.removeEventListener("loadeddata", onReady);
      video.removeEventListener("playing", onReady);
      video.removeEventListener("error", onError);
      video.removeEventListener("waiting", onWaiting);
      video.removeEventListener("stalled", onStalled);
      resetStreamRecovery();
      if (liveProfileRetryTimer) {
        clearTimeout(liveProfileRetryTimer);
        liveProfileRetryTimer = null;
      }
      if (liveConnectTimer) {
        clearTimeout(liveConnectTimer);
        liveConnectTimer = null;
      }
    };

    startAttempt();
  }

  function playPng(target, isCamera = false, streamToken = 0) {
    if (!target) return;
    stopLiveVideoMode();
    if (isCamera && isLivePage) {
      setLiveSourceBadge("Live PNG fallback", "fallback");
      setLiveAction("try", target);
    } else {
      setLiveAction("", null);
    }
    showSpinner(video);
    image.dataset.mode = "stream";
    image.dataset.streamToken = String(streamToken);
    setClipUiActive(false);
    setSpeedControlsVisible(true);
    video.preload = "none";
    crossFadeToImage();
    image.src = setPngSrc(target, isCamera);
    if (container) container.classList.add(LIVE_CLASS);
    if (pngTimer) clearInterval(pngTimer);
    pngTimer = setInterval(() => {
      if (image.dataset.streamToken !== String(streamToken)) return;
      image.src = setPngSrc(target, isCamera);
    }, refreshSeconds * 1000);
  }

  function playMjpg(target, isCamera = false, streamToken = 0) {
    if (!target) return;
    stopLiveVideoMode();
    if (isCamera && isLivePage) {
      setLiveSourceBadge("Live MJPEG fallback", "fallback");
      setLiveAction("try", target);
    } else {
      setLiveAction("", null);
    }
    if (pngTimer) {
      clearInterval(pngTimer);
      pngTimer = null;
    }
    showSpinner(video);
    image.dataset.mode = "stream";
    image.dataset.streamToken = String(streamToken);
    setClipUiActive(false);
    setSpeedControlsVisible(true);
    video.preload = "none";
    crossFadeToImage();
    const param = isCamera ? "camera" : "group";
    // Never force an on-demand recapture loop for live playback; it can hang
    // indefinitely on slow/broken web sources. Live video is handled via RTSP/HLS.
    // For everything else we stream the most recent frames and optionally kick
    // off a one-shot refresh.
    const route = "/stream.mjpg";
    image.src = `${route}?${param}=${encodeURIComponent(target)}&time=${Date.now()}`;
    if (container) container.classList.add(LIVE_CLASS);
  }

  function scheduleLive(name) {
    clearTimeout(liveTimer);
    liveTimer = setTimeout(() => play(name), IDLE_DELAY);
  }

  async function loadHdClip() {
    const url = video.dataset.hdSrc;
    if (!url) return;
    if (abortCtl) abortCtl.abort();
    abortCtl = new AbortController();
    const timer = setTimeout(() => abortCtl.abort(), 10000);
    try {
      showSpinner(video);
      const res = await fetch(url, { signal: abortCtl.signal });
      clearTimeout(timer);
      hideSpinner(video);
      if (!res.ok) {
        showErrorIndicator(video);
        return;
      }
      const blob = await res.blob();
      const objUrl = URL.createObjectURL(blob);
      const pos = video.currentTime;
      const paused = video.paused;
      if (res.headers.get("X-Clip-Status") === "waiting") {
        showBounce();
        const onHide = () => hideBounce();
        video.addEventListener("canplay", onHide, { once: true });
        video.addEventListener("error", onHide, { once: true });
      }
      const onLoad = () => {
        video.currentTime = Math.min(pos, video.duration || pos);
        if (!paused) video.play().catch(() => {});
        URL.revokeObjectURL(objUrl);
      };
      video.addEventListener("loadedmetadata", onLoad, { once: true });
      if (source) source.src = objUrl;
      video.load();
    } catch (_) {
      hideSpinner(video);
      hideBounce();
      showErrorIndicator(video);
    }
  }

  // Switch the UI to live MJPEG playback immediately. Archived clips are
  // skipped entirely so the image element always shows the current stream.
  function play(name) {
    if (!name) return;
    const now = Date.now();
    if (isLivePage && now - lastPlayBeaconAt > 10000) {
      lastPlayBeaconAt = now;
      sendClientBeacon("live_play", { name });
    }

    let selection = name;
    const shouldRotate =
      isLivePage &&
      !hasClipSource &&
      (forceAllRotator ||
        selection === "All" ||
        selection.startsWith("group-"));

    if (shouldRotate) {
      const root = forcedRotatorActive ? "All" : selection;
      const nextCamera = nextRotatedCamera(root);
      if (nextCamera) {
        selection = nextCamera;
        current = nextCamera;
        if (camSelect) {
          const hasCamera = Array.from(camSelect.options || []).some(
            (opt) => opt.value === nextCamera,
          );
          if (hasCamera) camSelect.value = nextCamera;
        }
        stopRotationTimer();
        rotationTimer = setTimeout(() => {
          play(root);
        }, ROTATION_DWELL_MS);
      } else {
        current = root;
      }
    } else {
      stopRotationTimer();
      rotationRoot = null;
      forcedRotatorActive = false;
      current = selection;
    }

    maybeWarmSelection(selection);
    syncLiveContext(selection);
    hideBounce();
    primeTransitionStill();
    const streamToken = ++activeStreamToken;

    clearLiveAutoUpgradeTimer();
    if (liveQuality === "auto") liveAutoStage = "first";
    setLiveAction("", null);

    if (shouldUseLiveVideo(selection)) {
      playLiveVideo(selection, streamToken);
      return;
    }

    const usePng = refreshSeconds > 1;
    if (selection === "All") {
      usePng
        ? playPng("all", false, streamToken)
        : playMjpg("all", false, streamToken);
    } else if (selection.startsWith("group-")) {
      const group = selection.slice(6);
      usePng
        ? playPng(group, false, streamToken)
        : playMjpg(group, false, streamToken);
    } else {
      usePng
        ? playPng(selection, true, streamToken)
        : playMjpg(selection, true, streamToken);
    }
  }

  if (camSelect) {
    camSelect.addEventListener("change", async () => {
      // Empty camera option means "rotate" for current group/all.
      const selected = camSelect.value;
      if (selected) {
        current = selected;
      } else {
        const navGroup = document.getElementById("nav-group-dropdown");
        const g = navGroup?.value || "all";
        current = g && g !== "all" ? `group-${g}` : "All";
      }

      syncLiveContext(current);

      if (isLivePage) {
        const u = new URL(window.location.href);
        if (
          forcedRotatorActive &&
          current &&
          current !== "All" &&
          !current.startsWith("group-")
        ) {
          forcedRotatorActive = false;
          u.searchParams.delete("rotator");
          u.searchParams.set("camera", current);
          u.searchParams.delete("group");
          history.replaceState(null, "", u.toString());
        } else if (
          forcedRotatorActive &&
          (current === "All" || current.startsWith("group-"))
        ) {
          // Keep the flag; URL may already include rotator=all.
        }
      }

      if (!hasClipSource) {
        // /live: show a still preview for the new target immediately, then
        // kick off capture and connect to the stream.
        cancelAdhocRefresh();
        const seq = (switchSeq += 1);
        showSpinner(video);
        spinnerMinUntil = Date.now() + 1000;
        // Preview runs in the background and is only applied if the stream
        // hasn't started yet for this switch sequence.
        showStillPreview(current, seq);
        triggerAdhocRefresh(current, seq);

        // Prefer a DVR-like clip experience when drilling into a camera/group.
        // After a short loop it drops back to live (or immediately via "Live").
        if (enterClipModeForSelection(current, seq)) return;

        play(current);
        return;
      }
      // Template pages: keep existing "idle-to-live" behavior.
      showClip();
      scheduleLive(current);
    });
  }

  if (speedSlider) {
    speedSlider.addEventListener("change", () => {
      // Apply speed changes immediately when already in live mode.
      if (container?.classList.contains(LIVE_CLASS)) play(current);
    });
  }

  syncLiveContext(current);

  if (source && source.src) {
    const onInteract = () => {
      clearTimeout(liveTimer);
      if (container?.classList.contains(LIVE_CLASS)) {
        showClip();
      }
      scheduleLive(current);
    };
    container?.addEventListener("mousemove", onInteract);
    container?.addEventListener("mousedown", onInteract);
    container?.addEventListener("touchstart", onInteract);
    scheduleLive(current);
  } else {
    play(current);
  }
}

document.addEventListener("DOMContentLoaded", () => {
  adjustFullHeight();
  try {
    initTilePlayer();
  } catch (err) {
    sendClientBeacon("init_exception", { message: String(err || "") });
    throw err;
  }
});
window.addEventListener("resize", adjustFullHeight);

export function updateCameraOptions(group) {
  const camSelect =
    document.getElementById("camera-selector") ||
    document.getElementById("nav-camera-dropdown");
  if (!camSelect) return;
  camSelect.innerHTML = "";
  if (!group || group === "all") {
    camSelect.style.display = "none";
    const opt = document.createElement("option");
    opt.value = "All";
    opt.textContent = "All";
    camSelect.appendChild(opt);
    camSelect.value = "All";
    return;
  }
  camSelect.style.display = "";
  const groupOpt = document.createElement("option");
  groupOpt.value = `group-${group}`;
  groupOpt.textContent = `Group: ${group}`;
  camSelect.appendChild(groupOpt);
  Object.entries(window.templateDetails || {})
    .filter(
      ([, det]) =>
        det.groups &&
        det.groups
          .split(",")
          .map((s) => s.trim())
          .includes(group),
    )
    .map(([cam]) => cam)
    .sort()
    .forEach((cam) => {
      const opt = document.createElement("option");
      opt.value = cam;
      opt.textContent = cam;
      camSelect.appendChild(opt);
    });
  camSelect.value = `group-${group}`;
}

export function changeGroup(group) {
  const navGroup = document.getElementById("nav-group-dropdown");
  if (!group) {
    group = navGroup ? navGroup.value : "all";
  }
  if (navGroup) navGroup.value = group;
  updateCameraOptions(group);
  window.currentCamera = null;
  window.currentGroup = group && group !== "all" ? group : null;
  if (typeof window.setLiveNavContext === "function") {
    window.setLiveNavContext({
      camera: null,
      group: window.currentGroup,
    });
  }
  const camSelect =
    document.getElementById("camera-selector") ||
    document.getElementById("nav-camera-dropdown");
  if (camSelect) camSelect.dispatchEvent(new Event("change"));
}

export function changeCamera(selectedValue) {
  const camSelect =
    document.getElementById("camera-selector") ||
    document.getElementById("nav-camera-dropdown");
  if (!camSelect || !selectedValue) return;
  if (camSelect.value !== selectedValue) camSelect.value = selectedValue;
  // If this is the same control currently dispatching a change event,
  // the tile player listener will already run. Otherwise trigger it.
  if (camSelect.id !== "nav-camera-dropdown") {
    camSelect.dispatchEvent(new Event("change"));
  }
}

window.changeGroup = changeGroup;
window.changeCamera = changeCamera;
window.updateCameraOptions = updateCameraOptions;
