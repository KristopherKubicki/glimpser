import { timeAgo, formatExactTime } from "./templates.js";

const video = document.getElementById("live-video");
const image = document.getElementById("live-image");
const templateDetailsContainer = document.getElementById("template-details");
const templateDetails = window.templateDetails || {};
let currentCamera = "All"; // Default to showing all cameras

// If only a single camera is available, default to that camera instead
const templateKeys = Object.keys(templateDetails);
if (templateKeys.length === 1) {
  currentCamera = templateKeys[0];
}

// Allow embedding the live view for a specific camera by reading the
// ``camera`` query parameter. When provided and valid, restrict the camera
// selector to that camera and start playback for it immediately.
const params = new URLSearchParams(window.location.search);
const requestedCamera = params.get("camera");
if (requestedCamera && templateDetails[requestedCamera]) {
  currentCamera = requestedCamera;
  const cameraSelector = document.getElementById("camera-selector");
  if (cameraSelector) {
    Array.from(cameraSelector.options).forEach((opt) => {
      if (opt.value !== requestedCamera) opt.remove();
    });
    cameraSelector.value = requestedCamera;
    cameraSelector.style.display = "none";
  }
}
let pngInterval;
let liveSwitchInterval;
let liveSwitchFunction;
let hlsInstance = null;
let loopHandler = null;
const speedContainer = document.getElementById("speed-container");
const videoOverlay = document.getElementById("video-overlay");
const loadingIndicator = document.getElementById("loading-indicator");
const playPauseIndicator = document.getElementById("play-pause-indicator");
const errorMessage = document.getElementById("error-message");
const playButton = document.getElementById("play-pause");
const offlineIndicator = document.getElementById("offline-indicator");
const offlineMessage = document.getElementById("offline-message");
const errorIndicator = document.getElementById("capture-error-indicator");
const errorIndicatorMessage = document.getElementById("capture-error-message");
const streamErrorIndicator = document.getElementById("stream-error-indicator");
const streamErrorMessage = document.getElementById("stream-error-message");
const seekBar = document.getElementById("seek-bar");
let isSeeking = false;

// Restore previously selected camera, source and speed from localStorage so
// reloading the page keeps user preferences. If the user specified a camera in
// the URL query string that takes precedence.
function loadSavedPreferences() {
  if (!requestedCamera) {
    const savedCam = localStorage.getItem("liveCamera");
    const camSelect = document.getElementById("camera-selector");
    if (
      savedCam &&
      camSelect &&
      camSelect.querySelector(`option[value="${savedCam}"]`)
    ) {
      currentCamera = savedCam;
      camSelect.value = savedCam;
    }
  }

  const sourceSelect = document.getElementById("video-source");
  const savedSource = localStorage.getItem("liveSource");
  if (
    savedSource &&
    sourceSelect &&
    sourceSelect.querySelector(`option[value="${savedSource}"]`)
  ) {
    sourceSelect.value = savedSource;
  }

  const savedSpeed = localStorage.getItem("playbackSpeed");
  const speedSlider = document.getElementById("speed-slider");
  if (savedSpeed && speedSlider) {
    speedSlider.value = savedSpeed;
  }
}

loadSavedPreferences();

function resetVideo() {
  if (hlsInstance) {
    hlsInstance.destroy();
    hlsInstance = null;
  }
  if (loopHandler) {
    video.removeEventListener("ended", loopHandler);
    loopHandler = null;
  }
  video.removeEventListener("ended", handleVideoEnded);
}

function showLoadingIndicator() {
  videoOverlay.style.display = "block";
  loadingIndicator.style.display = "block";
  playPauseIndicator.style.display = "none";
}

function hideLoadingIndicator() {
  loadingIndicator.style.display = "none";
  if (videoOverlay.style.display === "block") {
    setTimeout(() => {
      videoOverlay.style.display = "none";
    }, 500);
  }
}

function showPlayPauseIndicator(isPaused) {
  videoOverlay.style.display = "block";
  playPauseIndicator.style.display = "block";
  playPauseIndicator.textContent = isPaused ? " ▶ " : "▷";
  playButton.textContent = isPaused ? " ▶ " : "▷";
  loadingIndicator.style.display = "none";
  setTimeout(() => {
    playPauseIndicator.style.display = "none";
    if (loadingIndicator.style.display === "none") {
      videoOverlay.style.display = "none";
    }
  }, 500);
}

function showError(message) {
  errorMessage.textContent = message;
  errorMessage.style.display = "block";
  showStreamErrorIndicator(message);
  setTimeout(() => {
    errorMessage.style.display = "none";
  }, 5000);
}

function showOfflineIndicator(cameraName) {
  videoOverlay.style.display = "block";
  offlineIndicator.style.display = "block";
  offlineMessage.textContent = `Camera ${cameraName} is currently offline`;
  loadingIndicator.style.display = "none";
  playPauseIndicator.style.display = "none";
}

function hideOfflineIndicator() {
  offlineIndicator.style.display = "none";
  offlineMessage.textContent = "";
  if (
    loadingIndicator.style.display === "none" &&
    playPauseIndicator.style.display === "none"
  ) {
    videoOverlay.style.display = "none";
  }
}

function showCaptureErrorIndicator(cameraName) {
  videoOverlay.style.display = "block";
  errorIndicator.style.display = "block";
  errorIndicatorMessage.textContent = `Capture failed for ${cameraName}`;
  loadingIndicator.style.display = "none";
  playPauseIndicator.style.display = "none";
}

function hideCaptureErrorIndicator() {
  errorIndicator.style.display = "none";
  errorIndicatorMessage.textContent = "";
  if (
    loadingIndicator.style.display === "none" &&
    playPauseIndicator.style.display === "none" &&
    offlineIndicator.style.display === "none" &&
    streamErrorIndicator.style.display === "none"
  ) {
    videoOverlay.style.display = "none";
  }
}

function showStreamErrorIndicator(message) {
  videoOverlay.style.display = "block";
  streamErrorIndicator.style.display = "block";
  streamErrorMessage.textContent = message;
  loadingIndicator.style.display = "none";
  playPauseIndicator.style.display = "none";
}

function hideStreamErrorIndicator() {
  streamErrorIndicator.style.display = "none";
  streamErrorMessage.textContent = "";
  if (
    loadingIndicator.style.display === "none" &&
    playPauseIndicator.style.display === "none" &&
    offlineIndicator.style.display === "none" &&
    errorIndicator.style.display === "none"
  ) {
    videoOverlay.style.display = "none";
  }
}

video.addEventListener("waiting", showLoadingIndicator);
video.addEventListener("canplay", hideLoadingIndicator);
video.addEventListener("canplay", () => {
  image.style.display = "none";
});
// Hide the loading overlay when a PNG frame successfully loads so the
// viewer immediately sees the latest snapshot instead of an indefinite
// "Loading" message.
image.addEventListener("load", hideLoadingIndicator);
video.addEventListener("play", () => showPlayPauseIndicator(false));
video.addEventListener("pause", () => showPlayPauseIndicator(true));
video.addEventListener("error", (e) => {
  const msg = e.target.error ? e.target.error.message : "";
  const src = video.getAttribute("src");
  if (
    !src ||
    src.trim() === "" ||
    (msg && msg.includes("Empty src attribute"))
  ) {
    // Ignore errors from blank or cleared sources when switching cameras
    return;
  }
  if (
    (currentCamera === "All" || currentCamera.startsWith("group-")) &&
    typeof loopHandler === "function"
  ) {
    // Skip to the next camera when a clip fails to load
    loopHandler();
    return;
  }
  showError("Error loading video: " + msg);
  showLastScreenshot();
  setTimeout(() => {
    if (typeof updateFeed === "function") {
      updateFeed();
    }
  }, 2000);
});
image.addEventListener("error", () => {
  const src = image.getAttribute("src");
  if (!src || src.trim() === "") {
    // Ignore errors triggered from clearing the image source
    return;
  }
  if (src.includes("/stream.png")) {
    // For the PNG stream view, keep showing the last frame and retry
    setTimeout(() => {
      if (typeof updateFeed === "function") {
        updateFeed();
      }
    }, 2000);
    return;
  }
  showError("Error loading image");
  setTimeout(() => {
    if (typeof updateFeed === "function") {
      updateFeed();
    }
  }, 2000);
});

function changeCamera() {
  showLoadingIndicator();
  const cameraSelector = document.getElementById("camera-selector");
  const selectedValue = cameraSelector.value;
  // Check if the camera is connected
  let isConnected = checkCameraConnection(currentCamera);

  if (selectedValue === "All") {
    // Handle the "All" option separately
    currentCamera = "All";
    templateDetails["All"] = {
      url: "/stream.mp4", // Set the URL for the MP4 stream without a group
      groupCameras: Object.keys(templateDetails).filter((key) => key !== "All"), // Add all cameras
      // Add other necessary properties for the "All" group, if needed
    };
    isConnected = true;
  } else if (selectedValue.startsWith("group-")) {
    // Group is selected
    const groupName = selectedValue.split("group-")[1];
    currentCamera = "group-" + groupName; // Use a unique identifier for the group
    const groupCameras = Object.entries(templateDetails)
      .filter(
        ([camera, details]) =>
          details.groups &&
          details.groups
            .split(",")
            .map((s) => s.trim())
            .includes(groupName),
      )
      .map(([camera]) => camera);
    // Update the special URL for the group with the group query parameter
    templateDetails[currentCamera] = {
      url: `/stream.mp4?group=${groupName}`,
      groupCameras: groupCameras,
      groupName: groupName, // Add the groupName property
      // Add other necessary properties for the group
    };
    isConnected = true;
  } else {
    // Individual camera is selected
    currentCamera = selectedValue;
    isConnected = checkCameraConnection(currentCamera);
  }

  // Persist the chosen camera so the selection sticks across sessions
  localStorage.setItem("liveCamera", currentCamera);

  if (!isConnected) {
    showOfflineIndicator(currentCamera);
    hideLoadingIndicator();
    video.pause();
    video.src = "";
    image.src = "";
  } else {
    hideOfflineIndicator();
    showLastScreenshot();
    updateTemplateDetails();
    updateFeed(); // Make sure to update the video feed after changing the camera or group
    updateSpeedContainer();
  }
}

function updateTemplateDetails() {
  if (!detailsVisible) {
    templateDetailsContainer.style.display = "none";
    return;
  }
  const details = templateDetails[currentCamera];
  const isGroupView =
    currentCamera === "All" || currentCamera.startsWith("group-");

  if (!details || isGroupView) {
    templateDetailsContainer.style.display = "none";
    templateDetailsContainer.innerHTML = "";
    return;
  }

  video.title = details.last_caption;
  templateDetailsContainer.style.display = "block";
  templateDetailsContainer.innerHTML = `
        <div>
            <strong>Last Screenshot:</strong> ${details.last_screenshot_time || "N/A"}<br/>
            <strong>Last Video:</strong> ${details.last_video_time || "N/A"}<br/>
            <strong>Last Caption:</strong> ${details.last_caption || "N/A"}<br/>
            ${details.offline_since ? `<strong>Offline Since:</strong> ${details.offline_since}<br/>` : ""}
            ${details.capture_failed ? "<strong>Capture Failed</strong><br/>" : ""}
        </div>`;
}

function updateFeed() {
  resetVideo();
  const source = document.getElementById("video-source").value;
  const isConnected = checkCameraConnection(currentCamera);
  const details = templateDetails[currentCamera];
  updateSpeedContainer();
  hideStreamErrorIndicator();

  if (!isConnected) {
    showOfflineIndicator(currentCamera);
    hideCaptureErrorIndicator();
    hideLoadingIndicator();
    video.pause();
    video.src = "";
    image.src = "";
    showLastScreenshot();
    updateSeekBar();
    return;
  } else if (details && details.capture_failed) {
    hideOfflineIndicator();
    showCaptureErrorIndicator(currentCamera);
    hideLoadingIndicator();
    video.pause();
    video.src = "";
    image.src = "";
    showLastScreenshot();
    updateSeekBar();
    return;
  } else {
    hideOfflineIndicator();
    hideCaptureErrorIndicator();
    if (!["png", "mjpg", "motion"].includes(source)) {
      showLastScreenshot();
    }
  }

  if (source === "live" && details && details.snapshot_only) {
    playMJPG();
    return;
  }

  switch (source) {
    case "m3u8":
      playM3U8();
      break;
    case "loop":
      playLoop();
      break;
    case "png":
      playPNG();
      break;
    case "mp4":
      playMP4();
      break;
    case "live":
      playLive();
      break;
    case "mjpg":
      playMJPG();
      break;
    case "motion":
      playMotion();
      break;
    default:
      console.error("Invalid video source");
  }

  updateSeekBar();
}

function playM3U8() {
  resetVideo();
  video.style.display = "block";
  // HLS streams are live and not seekable
  const seekBar = document.getElementById("seek-bar");
  if (seekBar) {
    seekBar.style.visibility = "hidden";
    seekBar.style.pointerEvents = "none";
    seekBar.disabled = true;
  }

  image.style.display = "none";
  stopLiveSwitch();

  stopPNG();

  let m3u8Url;
  if (currentCamera.startsWith("group-")) {
    const groupName = currentCamera.split("group-")[1];
    m3u8Url = `/stream.m3u8?group=${encodeURIComponent(groupName)}`;
  } else if (currentCamera === "All") {
    m3u8Url = "/stream.m3u8";
  } else {
    m3u8Url = `/stream.m3u8?camera=${encodeURIComponent(currentCamera)}`;
  }

  if (Hls.isSupported()) {
    hlsInstance = new Hls();
    hlsInstance.loadSource(m3u8Url);
    hlsInstance.attachMedia(video);
    hlsInstance.on(Hls.Events.MANIFEST_PARSED, function () {
      video.play().catch((e) => console.error("Error playing video:", e));
    });
    hlsInstance.on(Hls.Events.ERROR, function (event, data) {
      console.error("HLS error:", data);
      if (data.fatal) {
        switch (data.type) {
          case Hls.ErrorTypes.NETWORK_ERROR:
            console.error(
              "Fatal network error encountered, trying to recover...",
            );
            hlsInstance.startLoad();
            break;
          case Hls.ErrorTypes.MEDIA_ERROR:
            console.error(
              "Fatal media error encountered, trying to recover...",
            );
            hlsInstance.recoverMediaError();
            break;
          default:
            console.error("Fatal error, cannot recover");
            hlsInstance.destroy();
            hlsInstance = null;
            break;
        }
      }
    });
  } else if (video.canPlayType("application/vnd.apple.mpegurl")) {
    video.src = m3u8Url;
    video.addEventListener("canplay", function () {
      video.play().catch((e) => console.error("Error playing video:", e));
    });
    video.addEventListener("error", function (e) {
      console.error("Video error:", video.error);
    });
  } else {
    console.error("HLS is not supported on this browser");
  }
}

function playLoop() {
  resetVideo();
  video.style.display = "block";

  image.style.display = "none";
  stopLiveSwitch();

  stopPNG();

  if (currentCamera.startsWith("group-") || currentCamera === "All") {
    // Handle both groups and the special "All" group
    let groupCameras;
    if (currentCamera === "All") {
      // If the "All" group is selected, get all camera names
      groupCameras = Object.keys(templateDetails).filter(
        (key) => key !== "All",
      );
    } else {
      // If a specific group is selected, get the cameras in that group
      const groupName = currentCamera.split("group-")[1];
      groupCameras = templateDetails["group-" + groupName].groupCameras;
    }

    let cameraIndex = 0;

    loopHandler = () => {
      if (cameraIndex >= groupCameras.length) {
        cameraIndex = 0; // Reset the index to loop through the cameras again
      }
      const cameraName = groupCameras[cameraIndex];
      video.src = `/last_video/${cameraName}`; // Update the video source with the current camera
      video.load();
      video.play();
      cameraIndex++; // Move to the next camera
    };

    loopHandler(); // Start the loop
    video.addEventListener("ended", loopHandler); // Continue the loop when the video ends
  } else {
    // Handling for individual cameras
    video.src = `/last_video/${currentCamera}`;
    video.load();
    video.play();
  }
}

function updateFrameTimestamp() {
  const container = document.querySelector(".video-container");
  if (!container) return;
  const details = templateDetails[currentCamera];
  if (!details || !details.last_screenshot_time) {
    container.removeAttribute("data-timestamp");
    container.removeAttribute("title");
    return;
  }
  container.dataset.originalTimestamp = details.last_screenshot_time;
  container.setAttribute(
    "data-timestamp",
    timeAgo(details.last_screenshot_time),
  );
  container.setAttribute(
    "title",
    formatExactTime(details.last_screenshot_time),
  );
}

function refreshPNG() {
  image.src =
    "/last_screenshot/" +
    encodeURIComponent(currentCamera) +
    "?time=" +
    new Date().getTime();
  updateFrameTimestamp();
}

function showLastScreenshot() {
  const ts = "?time=" + new Date().getTime();
  let url;
  if (currentCamera === "All") {
    // Show the most recent screenshot across all cameras
    url = "/stream.png" + ts;
  } else {
    // Display the latest screenshot for the selected camera or group
    url = "/last_screenshot/" + encodeURIComponent(currentCamera) + ts;
  }

  // Preload the image so the viewer always sees a frame when switching
  const pre = new Image();
  pre.onload = () => {
    image.src = pre.src;
  };
  pre.src = url;
  image.style.display = "block";
  updateFrameTimestamp();
}

function playMP4() {
  resetVideo();
  video.style.display = "block";
  stopLiveSwitch();
  stopPNG();
  if (currentCamera.startsWith("group-")) {
    // Special handling for groups
    const groupName = currentCamera.split("group-")[1];
    video.src = `/stream.mp4?group=${encodeURIComponent(groupName)}`;
  } else if (currentCamera === "All") {
    // Special handling for the "All" option
    video.src = "/stream.mp4";
  } else {
    // Stream a single camera
    video.src = `/stream.mp4?camera=${encodeURIComponent(currentCamera)}`;
  }
  video.load();
  video.play();

  // Remove any existing 'ended' event listeners
  video.removeEventListener("ended", handleVideoEnded);

  // Add an event listener for the 'ended' event
  video.addEventListener("ended", handleVideoEnded);
}

function handleVideoEnded() {
  if (currentCamera === "All" || currentCamera.startsWith("group-")) {
    // For "All" or group options, move to the next camera
    const groupCameras = templateDetails[currentCamera].groupCameras;
    const currentIndex = groupCameras.indexOf(video.dataset.currentCamera);
    const nextIndex = (currentIndex + 1) % groupCameras.length;
    const nextCamera = groupCameras[nextIndex];
    video.src = "/last_video/" + nextCamera;
    video.dataset.currentCamera = nextCamera;
  }
  video.load();
  video.play();
}

function playLive() {
  resetVideo();
  video.style.display = "block";
  // Live video cannot be scrubbed
  const seekBar = document.getElementById("seek-bar");
  if (seekBar) {
    seekBar.style.visibility = "hidden";
    seekBar.style.pointerEvents = "none";
    seekBar.disabled = true;
  }
  stopPNG();
  stopLiveSwitch();

  if (!(currentCamera.startsWith("group-") || currentCamera === "All")) {
    const details = templateDetails[currentCamera];
    if (details && details.snapshot_only) {
      playMJPG();
      return;
    }
  }

  if (currentCamera.startsWith("group-") || currentCamera === "All") {
    let groupCameras;
    if (currentCamera === "All") {
      groupCameras = Object.keys(templateDetails).filter(
        (key) => key !== "All",
      );
    } else {
      const groupName = currentCamera.split("group-")[1];
      groupCameras = templateDetails["group-" + groupName].groupCameras;
    }

    let cameraIndex = 0;
    liveSwitchFunction = () => {
      if (cameraIndex >= groupCameras.length) {
        cameraIndex = 0;
      }
      const cameraName = groupCameras[cameraIndex];
      video.src = "/live_video?camera=" + encodeURIComponent(cameraName);
      video.load();
      video.play();
      cameraIndex++;
    };

    const slider = document.getElementById("speed-slider");
    const speed = Math.pow(2, slider.value);
    liveSwitchFunction();
    liveSwitchInterval = setInterval(liveSwitchFunction, 10000 / speed);
  } else {
    video.src = "/live_video?camera=" + encodeURIComponent(currentCamera);
    video.load();
    video.play();
  }
}

function playPNG() {
  // When switching from video playback to PNG images, ensure any
  // ongoing video stream is stopped to avoid "media element" errors.
  resetVideo();
  video.pause();
  video.src = "";
  video.style.display = "none";
  image.style.display = "block";
  stopLiveSwitch();
  const slider = document.getElementById("speed-slider");
  const speed = Math.pow(2, slider.value);
  document.getElementById("seek-bar").style.display = "none";
  const seekBar = document.getElementById("seek-bar");
  // Structured log for easier scraping by Grafana Loki
  console.info(
    JSON.stringify({
      ts: Date.now(),
      ctx: "discover",
      msg: `seekBar:${seekBar},speed:${speed}`,
    }),
  );
  stopPNG();
  if (currentCamera.startsWith("group-")) {
    // Special handling for groups
    let cameraIndex = 0;
    const groupCameras = templateDetails[currentCamera].groupCameras;
    const refreshGroupPNG = () => {
      if (cameraIndex >= groupCameras.length) {
        cameraIndex = 0;
      }
      const cameraName = groupCameras[cameraIndex];
      image.src =
        "/last_screenshot/" + cameraName + "?time=" + new Date().getTime();
      cameraIndex++;
    };
    refreshGroupPNG();
    clearInterval(pngInterval);
    pngInterval = setInterval(refreshGroupPNG, 10000 / speed);
  } else if (currentCamera === "All") {
    // Special handling for the "All" option
    const refreshAllPNG = () => {
      image.src = "/stream.png?time=" + new Date().getTime();
    };
    refreshAllPNG();
    clearInterval(pngInterval);
    pngInterval = setInterval(refreshAllPNG, 10000 / speed);
  } else {
    // Original behavior for individual cameras
    refreshPNG();
    clearInterval(pngInterval);
    pngInterval = setInterval(refreshPNG, 10000 / speed);
  }
}

function playMJPG() {
  // Stop any existing video stream before showing MJPEG frames
  resetVideo();
  video.pause();
  video.src = "";
  video.style.display = "none";
  image.style.display = "block";
  // MJPEG streams are continuous images, disable scrubbing
  const seekBar = document.getElementById("seek-bar");
  if (seekBar) {
    seekBar.style.visibility = "hidden";
    seekBar.style.pointerEvents = "none";
    seekBar.disabled = true;
  }
  stopLiveSwitch();
  stopPNG();
  if (currentCamera.startsWith("group-")) {
    // Special handling for groups
    const groupName = currentCamera.split("group-")[1];
    image.src = `/stream.mjpg?group=${encodeURIComponent(groupName)}`;
  } else if (currentCamera === "All") {
    // Special handling for the "All" option
    image.src = "/stream.mjpg?group=all";
  } else {
    // URL for individual cameras
    image.src =
      "/stream.mjpg?camera=" +
      encodeURIComponent(currentCamera) +
      "&time=" +
      new Date().getTime();
  }
}

function playMotion() {
  // Stop any existing video stream before showing motion JPEG frames
  resetVideo();
  video.pause();
  video.src = "";
  video.style.display = "none";
  image.style.display = "block";
  const seekBar = document.getElementById("seek-bar");
  if (seekBar) {
    seekBar.style.visibility = "hidden";
    seekBar.style.pointerEvents = "none";
    seekBar.disabled = true;
  }
  stopLiveSwitch();
  stopPNG();
  if (currentCamera.startsWith("group-")) {
    // Special handling for groups
    const groupName = currentCamera.split("group-")[1];
    image.src = `/motion.mjpg?group=${encodeURIComponent(groupName)}`;
  } else if (currentCamera === "All") {
    // Special handling for the "All" option
    image.src = "/motion.mjpg?group=all";
  } else {
    // URL for individual cameras
    image.src =
      "/motion.mjpg?camera=" +
      encodeURIComponent(currentCamera) +
      "&time=" +
      new Date().getTime();
  }
}

function changeVideoSource() {
  const selector = document.getElementById("video-source");
  if (selector) {
    localStorage.setItem("liveSource", selector.value);
  }
  updateFeed();
}

function updatePlaybackSpeed() {
  const slider = document.getElementById("speed-slider");
  const speedDisplay = document.getElementById("speed-value");
  const speed = Math.pow(2, slider.value);
  localStorage.setItem("playbackSpeed", slider.value);
  video.playbackRate = parseFloat(speed.toFixed(2)); // Ensure the speed is a float with two decimal places
  speedDisplay.textContent = speed.toFixed(2) + "x"; // Update the text to show two decimal places

  // Adjust the refresh rate for the PNG stream based on the playback speed
  if (pngInterval) {
    clearInterval(pngInterval);
    pngInterval = setInterval(refreshPNG, 10000 / speed);
  }

  // Adjust the live group switch interval if active
  if (liveSwitchInterval && liveSwitchFunction) {
    clearInterval(liveSwitchInterval);
    liveSwitchInterval = setInterval(liveSwitchFunction, 10000 / speed);
  }

  speedDisplay.classList.add("highlight-speed");
  setTimeout(() => speedDisplay.classList.remove("highlight-speed"), 500);
}

function stopPNG() {
  if (pngInterval) {
    clearInterval(pngInterval);
    pngInterval = null;
  }
  image.src = "";
}

function stopLiveSwitch() {
  if (liveSwitchInterval) {
    clearInterval(liveSwitchInterval);
    liveSwitchInterval = null;
    liveSwitchFunction = null;
  }
}

function updateSpeedContainer() {
  if (!speedContainer) return;
  const source = document.getElementById("video-source").value;
  const isGroupView =
    currentCamera === "All" || currentCamera.startsWith("group-");
  let cameraCount = 0;
  if (isGroupView) {
    if (currentCamera === "All") {
      cameraCount = Object.keys(templateDetails).filter(
        (k) => k !== "All",
      ).length;
    } else {
      const details = templateDetails[currentCamera];
      cameraCount =
        details && details.groupCameras ? details.groupCameras.length : 0;
    }
  }
  const show = isGroupView && cameraCount > 1 && source !== "mjpg";
  speedContainer.style.visibility = show ? "visible" : "hidden";
  speedContainer.style.pointerEvents = show ? "auto" : "none";
  const slider = document.getElementById("speed-slider");
  if (slider) slider.disabled = !show;
}

function updateSeekBar() {
  const seekBar = document.getElementById("seek-bar");
  if (!seekBar) return;
  const source = document.getElementById("video-source").value;
  const isSingleCamera = !(
    currentCamera === "All" || currentCamera.startsWith("group-")
  );
  const show = isSingleCamera && (source === "mp4" || source === "loop");
  seekBar.style.visibility = show ? "visible" : "hidden";
  seekBar.style.pointerEvents = show ? "auto" : "none";
  seekBar.disabled = !show;
  if (show) {
    seekBar.max = video.duration || 0;
    seekBar.value = video.currentTime || 0;
  }
}

function checkCameraConnection(cameraName) {
  if (cameraName === "All" || cameraName.startsWith("group-")) {
    return true;
  }
  const camera = templateDetails[cameraName];
  if (!camera) {
    return false;
  }

  if (camera.offline_since && camera.offline_since !== "") {
    return false;
  }

  if (camera.capture_failed) {
    return false;
  }

  if (!camera.last_screenshot_time) {
    return false;
  }

  const lastScreenshotTime = new Date(camera.last_screenshot_time);
  const oneHourAgo = new Date(Date.now() - 60 * 60 * 1000);
  return lastScreenshotTime > oneHourAgo;
}

let captionInterval;

async function fetchLatestCaptions() {
  try {
    const resp = await fetch("/templates");
    if (!resp.ok) return;
    const data = await resp.json();
    for (const name in templateDetails) {
      if (data[name]) {
        templateDetails[name].last_caption = data[name].last_caption;
        templateDetails[name].last_caption_time = data[name].last_caption_time;
      }
    }
    updateTemplateDetails();
  } catch (err) {
    console.error("Failed to fetch captions", err);
  }
}

function startCaptionPolling() {
  fetchLatestCaptions();
  captionInterval = setInterval(fetchLatestCaptions, 15000);
}

// Initially show the latest screenshot and start the MJPG stream
showLastScreenshot();
updateTemplateDetails();
updateSpeedContainer();
updatePlaybackSpeed();
updateSeekBar();
playMJPG();
startCaptionPolling();
updateFrameTimestamp();
setInterval(updateFrameTimestamp, 60000);

if (seekBar) {
  video.addEventListener("loadedmetadata", () => {
    seekBar.max = video.duration || 0;
    seekBar.value = 0;
  });

  video.addEventListener("timeupdate", () => {
    if (!isSeeking) {
      seekBar.value = video.currentTime;
    }
  });

  seekBar.addEventListener("input", () => {
    video.currentTime = seekBar.value;
  });

  const stopSeek = () => {
    if (isSeeking) {
      isSeeking = false;
      video.play();
    }
  };

  seekBar.addEventListener("mousedown", () => {
    isSeeking = true;
    video.pause();
  });
  seekBar.addEventListener("mouseup", stopSeek);
  seekBar.addEventListener("touchstart", () => {
    isSeeking = true;
    video.pause();
  });
  seekBar.addEventListener("touchend", stopSeek);
}

if (toggleDetailsButton) {
  toggleDetailsButton.addEventListener("click", () => {
    detailsVisible = !detailsVisible;
    updateTemplateDetails();
  });
}

function togglePlayback() {
  if (video.paused) {
    video.play();
  } else {
    video.pause();
  }
}

function selectNextCamera() {
  const selector = document.getElementById("camera-selector");
  if (!selector) return;
  const options = Array.from(selector.options);
  const currentIndex = options.findIndex((opt) => opt.value === selector.value);
  const nextIndex = (currentIndex + 1) % options.length;
  selector.value = options[nextIndex].value;
  changeCamera();
}

function selectPreviousCamera() {
  const selector = document.getElementById("camera-selector");
  if (!selector) return;
  const options = Array.from(selector.options);
  const currentIndex = options.findIndex((opt) => opt.value === selector.value);
  const prevIndex = (currentIndex - 1 + options.length) % options.length;
  selector.value = options[prevIndex].value;
  changeCamera();
}

function selectNextSource() {
  const selector = document.getElementById("video-source");
  if (!selector) return;
  const options = Array.from(selector.options);
  const currentIndex = options.findIndex((opt) => opt.value === selector.value);
  const nextIndex = (currentIndex + 1) % options.length;
  selector.value = options[nextIndex].value;
  changeVideoSource();
}

function selectPreviousSource() {
  const selector = document.getElementById("video-source");
  if (!selector) return;
  const options = Array.from(selector.options);
  const currentIndex = options.findIndex((opt) => opt.value === selector.value);
  const prevIndex = (currentIndex - 1 + options.length) % options.length;
  selector.value = options[prevIndex].value;
  changeVideoSource();
}

document.addEventListener("keydown", (event) => {
  if (
    event.target.tagName === "INPUT" ||
    event.target.tagName === "SELECT" ||
    event.target.isContentEditable
  ) {
    return;
  }

  switch (event.key) {
    case " ": // Spacebar
    case "k":
      togglePlayback();
      event.preventDefault();
      break;
    case "ArrowRight":
    case "l":
      selectNextCamera();
      event.preventDefault();
      break;
    case "ArrowLeft":
    case "j":
      selectPreviousCamera();
      event.preventDefault();
      break;
    case "ArrowUp":
      selectPreviousSource();
      event.preventDefault();
      break;
    case "ArrowDown":
      selectNextSource();
      event.preventDefault();
      break;
  }
});

// Expose handlers used by inline event attributes
window.changeCamera = changeCamera;
window.changeVideoSource = changeVideoSource;
window.updatePlaybackSpeed = updatePlaybackSpeed;
window.selectNextCamera = selectNextCamera;
window.selectPreviousCamera = selectPreviousCamera;
window.selectNextSource = selectNextSource;
window.selectPreviousSource = selectPreviousSource;
window.togglePlayback = togglePlayback;

// --- Mobile swipe handling ---
// Allow quick camera changes on touch devices by swiping left or right
let touchStartX = null;
let touchStartY = null;

function handleTouchStart(event) {
  const firstTouch = event.touches[0];
  touchStartX = firstTouch.clientX;
  touchStartY = firstTouch.clientY;
}

function handleTouchEnd(event) {
  if (touchStartX === null || touchStartY === null) return;

  const touchEndX = event.changedTouches[0].clientX;
  const touchEndY = event.changedTouches[0].clientY;
  const diffX = touchEndX - touchStartX;
  const diffY = touchEndY - touchStartY;

  // Horizontal swipe changes the camera
  if (Math.abs(diffX) > 50 && Math.abs(diffX) > Math.abs(diffY)) {
    if (diffX > 0) {
      selectPreviousCamera();
    } else {
      selectNextCamera();
    }
  } else if (Math.abs(diffY) > 50 && Math.abs(diffY) > Math.abs(diffX)) {
    // Vertical swipe changes the media source
    if (diffY > 0) {
      selectNextSource();
    } else {
      selectPreviousSource();
    }
  }

  touchStartX = null;
  touchStartY = null;
}

document.addEventListener("touchstart", handleTouchStart, { passive: true });
document.addEventListener("touchend", handleTouchEnd, { passive: true });
