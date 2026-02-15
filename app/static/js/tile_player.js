import { showSpinner, hideSpinner, showErrorIndicator } from "./video.js";

function safePlay(el) {
  const p = el.play?.();
  if (p && typeof p.catch === "function") p.catch(() => {});
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

  const preferredCamera =
    typeof window.currentCamera === "string" ? window.currentCamera : "";
  const preferredGroup =
    typeof window.currentGroup === "string" ? window.currentGroup : "";
  const realCameras = Object.keys(window.templateDetails || {}).filter(
    (name) => name !== "All",
  );
  const singleCamera = realCameras.length === 1 ? realCameras[0] : "";
  let current =
    preferredCamera && window.templateDetails?.[preferredCamera]
      ? preferredCamera
      : preferredGroup && preferredGroup !== "all"
        ? `group-${preferredGroup}`
        : isLivePage && singleCamera
          ? singleCamera
          : camSelect && camSelect.value
            ? camSelect.value
            : "All";

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

  let flashShield = container?.querySelector("#flash-shield") || null;
  if (!flashShield && container) {
    flashShield = document.createElement("div");
    flashShield.id = "flash-shield";
    flashShield.className = "flash-shield";
    container.appendChild(flashShield);
  }

  let _lumaCanvas = null;
  let _lumaCtx = null;

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

    // Gentle normalization: keep it subtle so it doesn't look "filtered".
    const scale = _clamp(0.75, FLASH_TARGET_LUMA / Math.max(luma, 0.05), 1.25);
    const contrast = _clamp(0.9, 1.05 - Math.abs(luma - 0.5) * 0.25, 1.05);
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
      const a = _clamp(0, Math.max(hi, lo) * 1.2, 0.22);
      if (a <= 0.001) {
        flashShield.style.backgroundColor = "rgba(0,0,0,0)";
      } else if (hi >= lo) {
        flashShield.style.backgroundColor = `rgba(0,0,0,${a.toFixed(3)})`;
      } else {
        flashShield.style.backgroundColor = `rgba(255,255,255,${a.toFixed(3)})`;
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

  const speedContainer = document.getElementById("speed-container");

  function setSpeedControlsVisible(visible) {
    if (!speedContainer) return;
    speedContainer.style.display = visible ? "" : "none";
  }

  function updateSpeedLabel() {
    if (!speedValue || !speedSlider) return;
    const secs = Math.max(1, parseInt(speedSlider.value, 10) || 1);
    refreshSeconds = secs;
    speedValue.textContent =
      secs === 60 ? "1fpm" : `${(1 / secs).toFixed(2)}fps`;
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
  const hasClipSource = Boolean(source && source.src);
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
      if (flashShield) flashShield.style.backgroundColor = "rgba(0,0,0,0.06)";
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
      new Promise((resolve) => setTimeout(() => resolve(false), 750)),
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
      video.style.display = "block";
      image.style.display = "none";
      hideSpinner(video);
      // Fade in once we have the first frame.
      requestAnimationFrame(() => {
        video.style.opacity = "1";
      });
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
    video.style.display = "none";
    image.style.display = "block";
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
    video.style.display = "none";
    image.style.display = "block";
    const param = isCamera ? "camera" : "group";
    const route = isCamera ? "/fast_stream.mjpg" : "/stream.mjpg";
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
    current = name;
    maybeWarmSelection(name);
    syncLiveContext(name);
    hideBounce();
    const streamToken = ++activeStreamToken;

    clearLiveAutoUpgradeTimer();
    if (liveQuality === "auto") liveAutoStage = "first";
    setLiveAction("", null);

    if (shouldUseLiveVideo(name)) {
      playLiveVideo(name, streamToken);
      return;
    }

    const usePng = refreshSeconds > 1;
    if (name === "All") {
      usePng
        ? playPng("all", false, streamToken)
        : playMjpg("all", false, streamToken);
    } else if (name.startsWith("group-")) {
      const group = name.slice(6);
      usePng
        ? playPng(group, false, streamToken)
        : playMjpg(group, false, streamToken);
    } else {
      usePng
        ? playPng(name, true, streamToken)
        : playMjpg(name, true, streamToken);
    }
  }

  if (camSelect) {
    camSelect.addEventListener("change", async () => {
      current = camSelect.value;
      syncLiveContext(current);
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
  initTilePlayer();
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
