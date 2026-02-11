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
  let current =
    preferredCamera && window.templateDetails?.[preferredCamera]
      ? preferredCamera
      : camSelect && camSelect.value
        ? camSelect.value
        : "All";

  let abortCtl;
  let liveTimer;

  const container = video.parentElement;

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
  image.addEventListener("load", () => {
    setMediaAspect(image.naturalWidth, image.naturalHeight);
    // Only hide the spinner when we're receiving actual stream frames.
    // When switching cameras, we often show a "last screenshot" preview first.
    if (image.dataset.mode === "stream") {
      const remaining = spinnerMinUntil - Date.now();
      if (remaining > 0) {
        setTimeout(() => hideSpinner(video), remaining);
      } else {
        hideSpinner(video);
      }
    }
  });

  const fsButton = document.getElementById("fullscreen-toggle");
  if (fsButton) {
    // Avoid showing both the browser's native fullscreen control (inside the
    // video controls) and our custom overlay button.
    video.setAttribute("controlsList", "nofullscreen");
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

  function showClip() {
    if (pngTimer) {
      clearInterval(pngTimer);
      pngTimer = null;
    }
    image.style.display = "none";
    video.style.display = "block";
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
      ensureClipControls();
      if (clipControls) clipControls.style.display = active ? "flex" : "none";
    }
  }

  function setVideoSrc(url) {
    // Use the <video> element directly; live.html's <source> has no src.
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

  function playPng(target, isCamera = false) {
    if (!target) return;
    showSpinner(video);
    image.dataset.mode = "stream";
    setClipUiActive(false);
    video.preload = "none";
    video.style.display = "none";
    image.style.display = "block";
    image.src = setPngSrc(target, isCamera);
    if (container) container.classList.add(LIVE_CLASS);
    if (pngTimer) clearInterval(pngTimer);
    pngTimer = setInterval(() => {
      image.src = setPngSrc(target, isCamera);
    }, refreshSeconds * 1000);
  }

  function playMjpg(target, isCamera = false) {
    if (!target) return;
    if (pngTimer) {
      clearInterval(pngTimer);
      pngTimer = null;
    }
    showSpinner(video);
    image.dataset.mode = "stream";
    setClipUiActive(false);
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
    hideBounce();
    const usePng = refreshSeconds > 1;
    if (name === "All") {
      usePng ? playPng("all") : playMjpg("all");
    } else if (name.startsWith("group-")) {
      const group = name.slice(6);
      usePng ? playPng(group) : playMjpg(group);
    } else {
      usePng ? playPng(name, true) : playMjpg(name, true);
    }
  }

  if (camSelect) {
    camSelect.addEventListener("change", async () => {
      current = camSelect.value;
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
  const camSelect =
    document.getElementById("camera-selector") ||
    document.getElementById("nav-camera-dropdown");
  if (camSelect) camSelect.dispatchEvent(new Event("change"));
}

window.changeGroup = changeGroup;
window.updateCameraOptions = updateCameraOptions;
