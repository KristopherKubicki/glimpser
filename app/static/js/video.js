import { setCaptionsVisibility } from "./templates.js";

let scrubTooltip;

function createScrubTooltip() {
  if (!scrubTooltip) {
    scrubTooltip = document.createElement("div");
    scrubTooltip.className = "scrub-tooltip";
    document.body.appendChild(scrubTooltip);
  }
}

function updateScrubTooltip(time, e) {
  if (!scrubTooltip) return;
  const formatted = new Date(time * 1000).toISOString().substring(11, 19);
  scrubTooltip.textContent = formatted;
  const offset = 8;
  const width = scrubTooltip.offsetWidth;
  let left = e.pageX + offset;
  if (left + width > window.innerWidth) {
    left = e.pageX - width - offset;
  }
  scrubTooltip.style.left = `${left}px`;
  scrubTooltip.style.top = `${e.pageY + offset}px`;
  scrubTooltip.classList.add("visible");
}

function hideScrubTooltip() {
  if (scrubTooltip) scrubTooltip.classList.remove("visible");
}

// Prefetch queue to avoid loading many clips at once
let prefetchQueue = [];
let processing = false;
let queueDelay = 1000;
const spinnerFrames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"];

function showSpinner(video) {
  const spinner = video.parentElement?.querySelector(".loading-spinner");
  if (!spinner || spinner.dataset.active === "true") return;
  let i = 0;
  spinner.textContent = spinnerFrames[i];
  spinner.classList.add("visible");
  spinner.dataset.active = "true";
  const id = setInterval(() => {
    i = (i + 1) % spinnerFrames.length;
    spinner.textContent = spinnerFrames[i];
  }, 100);
  spinner.dataset.intervalId = id.toString();
}

function hideSpinner(video) {
  const spinner = video.parentElement?.querySelector(".loading-spinner");
  if (!spinner || spinner.dataset.active !== "true") return;
  clearInterval(Number(spinner.dataset.intervalId));
  spinner.dataset.active = "false";
  spinner.classList.remove("visible");
}

export function setQueueDelay(ms) {
  queueDelay = ms;
}

export function enqueueClip(video) {
  if (!video.dataset.hdSrc || video.dataset.hdLoaded === "true") return;
  if (prefetchQueue.includes(video)) return;
  prefetchQueue.push(video);
  showSpinner(video);
  if (!processing) processQueue();
}

export function clearPrefetchQueue() {
  prefetchQueue = [];
  processing = false;
}

function processQueue() {
  const vid = prefetchQueue.shift();
  if (!vid) {
    processing = false;
    return;
  }
  processing = true;
  const src = vid.querySelector("source");
  if (src) {
    src.src = vid.dataset.hdSrc;
    vid.dataset.hdLoaded = "true";
    vid.addEventListener("canplay", () => hideSpinner(vid), { once: true });
    vid.addEventListener("error", () => hideSpinner(vid), { once: true });
    vid.load();
  }
  setTimeout(processQueue, queueDelay);
}

function safePlay(el) {
  const promise = el.play();
  if (promise && typeof promise.catch === "function") {
    promise.catch((err) => {
      if (err.name !== "AbortError") {
        console.error("Error playing video:", err);
      }
    });
  }
}

export function initVideoControls() {
  document.addEventListener("DOMContentLoaded", () => {
    setupStatusPageVideoHover();
    setupCaptionsPageVideoHover();
    setupVideoControls();

    const playAllButton = document.getElementById("play-all-button");
    const liveAllButton = document.getElementById("live-all-button");
    let playAllActive = false;
    let playAllObserver;

    if (liveAllButton) liveAllButton.style.display = "none";

    function handlePlayAll(entries) {
      entries.forEach((entry) => {
        if (!playAllActive) return;
        if (entry.isIntersecting) {
          safePlay(entry.target);
        } else {
          entry.target.pause();
        }
      });
    }

    if (playAllButton) {
      playAllButton.addEventListener("click", () => {
        const videos = document.querySelectorAll(".templateDiv video");
        if (playAllActive) {
          if (playAllObserver) playAllObserver.disconnect();
          videos.forEach((video) => {
            const name = video.getAttribute("data-name");
            video.pause();
            video.querySelector("source").src = `/last_video/${name}`;
            video.dataset.hdLoaded = "false";
          });
          playAllButton.textContent = "Play All";
          if (liveAllButton) liveAllButton.style.display = "none";
        } else {
          playAllObserver = new IntersectionObserver(handlePlayAll, {
            threshold: 0.25,
          });
          videos.forEach((video) => {
            const name = video.getAttribute("data-name");
            const src = video.querySelector("source");
            src.src = `/clip/${name}`;
            video.dataset.hdLoaded = "true";
            video.removeAttribute("src");
            video.poster = `/last_screenshot/${name}`;
            playAllObserver.observe(video);
            video.load();
            safePlay(video);
          });
          setCaptionsVisibility(false);
          playAllButton.textContent = "Pause All";
          if (liveAllButton) liveAllButton.style.display = "inline-block";
        }
        playAllActive = !playAllActive;
      });
    }

    if (liveAllButton) {
      liveAllButton.addEventListener("click", () => {
        const videos = document.querySelectorAll(".templateDiv video");
        if (playAllObserver) playAllObserver.disconnect();
        videos.forEach((video) => {
          const name = video.getAttribute("data-name");
          video.pause();
          video.src = "";
          video.poster = `/last_screenshot/${name}?t=${Date.now()}`;
          video.load();
        });
        playAllActive = false;
        playAllButton.textContent = "Play All";
        liveAllButton.style.display = "none";
      });
    }

    setInterval(updateVideoSources, 60000 * 30);
  });

  window.__onGCastApiAvailable = function (isAvailable) {
    if (isAvailable) initializeCastApi();
  };
}

export function updateVideoSources() {
  const videos = document.querySelectorAll(".templateDiv video");
  videos.forEach((video) => {
    const name = video.getAttribute("data-name");
    const timestamp = new Date().getTime();
    video.querySelector("source").src = `/clip/${name}?t=${timestamp}`;
    video.poster = `/last_screenshot/${name}?t=${timestamp}`;
  });
}

export function initVisibilityHandler() {
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) {
      document.querySelectorAll("video").forEach((v) => v.pause());
      clearPrefetchQueue();
    }
  });
}

export function setupVideoControls() {
  const video = document.getElementById("live-video");
  if (!video) return;

  const playPauseButton = document.getElementById("play-pause");
  const muteButton = document.getElementById("mute");
  const fullScreenButton = document.getElementById("full-screen");
  const seekBar = document.getElementById("seek-bar");
  const volumeBar = document.getElementById("volume-bar");
  const castButton = document.getElementById("cast-button");
  const rotateButton = document.getElementById("rotate-video");
  let rotateAngle = 0;

  if (playPauseButton) {
    playPauseButton.addEventListener("click", () => {
      if (video.paused) {
        safePlay(video);
      } else {
        video.pause();
      }
    });
  }
  if (muteButton) {
    muteButton.addEventListener("click", () => {
      video.muted = !video.muted;
    });
  }
  if (fullScreenButton) {
    fullScreenButton.addEventListener("click", () => {
      if (video.requestFullscreen) video.requestFullscreen();
      else if (video.mozRequestFullScreen) video.mozRequestFullScreen();
      else if (video.webkitRequestFullscreen) video.webkitRequestFullscreen();
      else if (video.msRequestFullscreen) video.msRequestFullscreen();
    });
  }
  if (rotateButton) {
    rotateButton.addEventListener("click", () => {
      rotateAngle = (rotateAngle + 90) % 360;
      const container = document.querySelector(".video-container");
      if (container) container.style.transform = `rotate(${rotateAngle}deg)`;
    });
  }
  if (seekBar) {
    seekBar.addEventListener("change", () => {
      video.currentTime = video.duration * (seekBar.value / 100);
    });
    video.addEventListener("timeupdate", () => {
      seekBar.value = (100 / video.duration) * video.currentTime;
    });
  }
  if (volumeBar) {
    volumeBar.addEventListener("change", () => {
      video.volume = volumeBar.value;
    });
  }
  if (castButton) {
    castButton.addEventListener("click", startCasting);
  }

  document.addEventListener("keydown", (e) => {
    const tag = e.target.tagName.toLowerCase();
    if (tag === "input" || tag === "textarea") return;
    switch (e.key) {
      case " ": // Spacebar
      case "k":
        e.preventDefault();
        if (video.paused) {
          safePlay(video);
        } else {
          video.pause();
        }
        break;
      case "m":
        video.muted = !video.muted;
        break;
      case "f":
        if (video.requestFullscreen) video.requestFullscreen();
        else if (video.mozRequestFullScreen) video.mozRequestFullScreen();
        else if (video.webkitRequestFullscreen) video.webkitRequestFullscreen();
        else if (video.msRequestFullscreen) video.msRequestFullscreen();
        break;
      case "ArrowLeft":
      case "ArrowRight": {
        const selector = document.getElementById("camera-selector");
        if (!selector) break;
        const step = e.key === "ArrowLeft" ? -1 : 1;
        const newIndex = selector.selectedIndex + step;
        if (newIndex >= 0 && newIndex < selector.options.length) {
          selector.selectedIndex = newIndex;
          if (typeof changeCamera === "function") changeCamera();
        }
        break;
      }
      case "[":
      case "]": {
        const slider = document.getElementById("speed-slider");
        if (!slider) break;
        const step = parseFloat(slider.step) || 1;
        const delta = e.key === "[" ? -step : step;
        const newValue = Math.min(
          parseFloat(slider.max),
          Math.max(parseFloat(slider.min), parseFloat(slider.value) + delta),
        );
        slider.value = newValue;
        if (typeof updatePlaybackSpeed === "function") updatePlaybackSpeed();
        break;
      }
      default:
        break;
    }
  });

  const container = video.closest(".video-container");
  const controls = container?.querySelector(".video-controls");
  let fadeTimeout;
  let autoplayTimeout;

  const showControls = () => {
    if (controls) controls.classList.remove("fade-out");
    clearTimeout(fadeTimeout);
    clearTimeout(autoplayTimeout);
    fadeTimeout = setTimeout(() => {
      if (controls) controls.classList.add("fade-out");
    }, 3000);
    autoplayTimeout = setTimeout(() => {
      video.playbackRate = 0.5;
      if (video.paused) safePlay(video);
    }, 60000);
  };

  if (container) {
    ["mousemove", "touchstart", "click"].forEach((evt) =>
      container.addEventListener(evt, showControls),
    );
    showControls();
  }
}

export function setupStatusPageVideoHover() {
  const thumbnailVideoCells = document.querySelectorAll(".thumbnail-video");
  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        const vid = entry.target;
        if (entry.isIntersecting) {
          enqueueClip(vid);
        }
      });
    },
    { threshold: 0.5 },
  );

  thumbnailVideoCells.forEach((cell) => {
    const img = cell.querySelector("img.thumbnail");
    const video = cell.querySelector("video.hover-video");
    if (img && video) {
      observer.observe(video);
      let targetTime = 0;
      let rafId;

      const step = () => {
        if (!Number.isNaN(targetTime)) {
          video.currentTime += (targetTime - video.currentTime) * 0.4;
        }
        rafId = requestAnimationFrame(step);
      };

      const scrub = (e) => {
        const rect = cell.getBoundingClientRect();
        const ratio = (e.clientX - rect.left) / rect.width;
        const clamped = Math.max(0, Math.min(1, ratio));
        if (!Number.isNaN(video.duration)) {
          targetTime = video.duration * clamped;
          updateScrubTooltip(targetTime, e);
        }
      };

      let resetTimeout;
      let hoverTimer;

      cell.addEventListener("mouseenter", (e) => {
        clearTimeout(resetTimeout);
        hoverTimer = setTimeout(() => enqueueClip(video), 500);
        img.style.display = "none";
        video.style.display = "block";
        createScrubTooltip();
        // Load metadata on first hover so currentTime can be set
        if (video.readyState === 0) {
          video.load();
          const onLoad = () => {
            scrub(e);
            video.removeEventListener("loadedmetadata", onLoad);
          };
          video.addEventListener("loadedmetadata", onLoad);
        } else {
          scrub(e);
        }
        video.pause();
        if (!rafId) rafId = requestAnimationFrame(step);
      });

      cell.addEventListener("mousemove", scrub);

      cell.addEventListener("mouseleave", () => {
        clearTimeout(hoverTimer);
        hideScrubTooltip();
        cancelAnimationFrame(rafId);
        rafId = null;
        resetTimeout = setTimeout(() => {
          video.pause();
          video.currentTime = 0;
          video.style.display = "none";
          img.style.display = "block";
        }, 1000); // restore screenshot a bit after leaving
      });
    }
  });
}

export function setupCaptionsPageVideoHover() {
  const containers = document.querySelectorAll(
    ".captions-page .video-container",
  );
  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        const vid = entry.target;
        if (entry.isIntersecting) {
          enqueueClip(vid);
        }
      });
    },
    { threshold: 0.5 },
  );

  containers.forEach((container) => {
    const video = container.querySelector("video.hover-video");
    if (!video) return;
    observer.observe(video);
    let targetTime = 0;
    let rafId;

    const step = () => {
      if (!Number.isNaN(targetTime)) {
        video.currentTime += (targetTime - video.currentTime) * 0.4;
      }
      rafId = requestAnimationFrame(step);
    };

    const scrub = (e) => {
      const rect = container.getBoundingClientRect();
      const ratio = (e.clientX - rect.left) / rect.width;
      const clamped = Math.max(0, Math.min(1, ratio));
      if (!Number.isNaN(video.duration)) {
        targetTime = video.duration * clamped;
      }
    };

    container.addEventListener("mouseenter", (e) => {
      if (video.readyState === 0) {
        video.load();
        const onLoad = () => {
          scrub(e);
          video.removeEventListener("loadedmetadata", onLoad);
        };
        video.addEventListener("loadedmetadata", onLoad);
      } else {
        scrub(e);
      }
      video.pause();
      if (!rafId) rafId = requestAnimationFrame(step);
    });

    container.addEventListener("mousemove", scrub);

    container.addEventListener("mouseleave", () => {
      hideScrubTooltip();
      cancelAnimationFrame(rafId);
      rafId = null;
      video.pause();
      video.currentTime = 0;
    });
  });
}

export function initializeCastApi() {
  cast.framework.CastContext.getInstance().setOptions({
    receiverApplicationId: chrome.cast.media.DEFAULT_MEDIA_RECEIVER_APP_ID,
    autoJoinPolicy: chrome.cast.AutoJoinPolicy.ORIGIN_SCOPED,
  });
}

export function startCasting() {
  const castSession =
    cast.framework.CastContext.getInstance().getCurrentSession();
  if (castSession) {
    const mediaInfo = new chrome.cast.media.MediaInfo(
      document.getElementById("live-video").src,
      "video/mp4",
    );
    const request = new chrome.cast.media.LoadRequest(mediaInfo);
    castSession.loadMedia(request).then(
      () =>
        // Structured log for cast start
        console.info(
          JSON.stringify({
            ts: Date.now(),
            ctx: "discover",
            msg: "Cast started",
          }),
        ),
      (errorCode) => console.error("Error code: " + errorCode),
    );
  } else {
    // Structured log when no cast session is active
    console.info(
      JSON.stringify({
        ts: Date.now(),
        ctx: "discover",
        msg: "No active cast session",
      }),
    );
  }
}

// expose queue functions for other modules
window.enqueueClip = enqueueClip;
window.setQueueDelay = setQueueDelay;
window.clearPrefetchQueue = clearPrefetchQueue;
export { showSpinner, hideSpinner };
