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
    setupVideoControls();

    const playAllButton = document.getElementById("play-all-button");
    const liveAllButton = document.getElementById("live-all-button");
    let playAllActive = false;
    let liveAllActive = false;
    let playAllObserver;

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
            const src = video.querySelector("source");
            src.src = `/last_video/${name}`;
            video.poster = `/last_screenshot/${name}`;
            video.load();
            video.pause();
            video.currentTime = 0;
            video.poster = `/last_screenshot/${name}?t=${Date.now()}`;
            video.load();
          });
          playAllButton.textContent = "Play All";
        } else {
          playAllObserver = new IntersectionObserver(handlePlayAll, {
            threshold: 0.25,
          });
          videos.forEach((video) => {
            playAllObserver.observe(video);
            safePlay(video);
          });
          playAllButton.textContent = "Stop";
        }
        playAllActive = !playAllActive;
      });
    }

    if (liveAllButton) {
      liveAllButton.addEventListener("click", () => {
        const videos = document.querySelectorAll(".templateDiv video");
        videos.forEach((video) => {
          const name = video.getAttribute("data-name");
          const source = video.querySelector("source");
          if (liveAllActive) {
            source.src = `/last_video/${name}`;
            video.poster = `/last_screenshot/${name}`;
            video.load();
            video.pause();
            video.currentTime = 0;
          } else {
            source.src = `/live_video?camera=${encodeURIComponent(name)}`;
            video.poster = "";
            video.load();
            safePlay(video);
          }
        });
        liveAllButton.textContent = liveAllActive ? "Live All" : "Stop Live";
        liveAllActive = !liveAllActive;
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
    video.querySelector("source").src = `/last_video/${name}?t=${timestamp}`;
    video.poster = `/last_screenshot/${name}?t=${timestamp}`;
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
}

export function setupStatusPageVideoHover() {
  const thumbnailVideoCells = document.querySelectorAll(".thumbnail-video");
  thumbnailVideoCells.forEach((cell) => {
    const img = cell.querySelector("img.thumbnail");
    const video = cell.querySelector("video.hover-video");
    if (img && video) {
      cell.addEventListener("mouseenter", () => {
        img.style.display = "none";
        video.style.display = "block";
        safePlay(video);
      });
      cell.addEventListener("mouseleave", () => {
        video.pause();
        video.currentTime = 0;
        video.style.display = "none";
        img.style.display = "block";
      });
    }
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
