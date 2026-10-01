import { attemptAutoLogin } from "./login.js";
import { safePlay, setClipSrc as setClipSrcVideo } from "./video_utils.js";
import { getCameraNames as getCameraNamesUtil } from "./camera_utils.js";
import { parseTimestamp } from "./time_utils.js";
import {
  updateFrameTimestamp as updateFrameTimestampUtil,
  setTimestampVisibility as setTimestampVisibilityUtil,
} from "./timestamp_utils.js";

const video = document.getElementById("live-video");

function setClipSrc(cameraName) {
  setClipSrcVideo(video, cameraName);
}
const image = document.getElementById("live-image");
const templateDetailsContainer = document.getElementById("template-details");
const templateDetails = window.templateDetails || {};
let currentCamera = "All"; // Default to showing all cameras

// If only a single camera is available, default to that camera instead
const templateKeys = Object.keys(templateDetails);
if (templateKeys.length === 1) {
  currentCamera = templateKeys[0];
}

// Ensure the synthetic "All" group is defined on page load so switching the
// video source works even before the camera selector is changed. Without this
// initialization, functions like playPNG() would crash when currentCamera is
// "All" because templateDetails["All"] would be undefined.
if (!templateDetails["All"]) {
  templateDetails["All"] = {
    url: "/stream.mp4",
    groupCameras: templateKeys,
  };
}

function getCameraNames() {
  return getCameraNamesUtil(templateDetails);
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
const controlsWrapper = document.getElementById("controls-wrapper");
const videoOverlay = document.getElementById("video-overlay");
const loadingIndicator = document.getElementById("loading-indicator");
const playPauseIndicator = document.getElementById("play-pause-indicator");
const errorMessage = document.getElementById("error-message");
const playButton = document.getElementById("play-pause");
const toggleDetailsButton = document.getElementById("toggle-details");
const offlineIndicator = document.getElementById("offline-indicator");
const offlineMessage = document.getElementById("offline-message");
const errorIndicator = document.getElementById("capture-error-indicator");
const errorIndicatorMessage = document.getElementById("capture-error-message");
const streamErrorIndicator = document.getElementById("stream-error-indicator");
const streamErrorMessage = document.getElementById("stream-error-message");
const seekBar = document.getElementById("seek-bar");
const jogShuttle = document.getElementById("jog-shuttle");
// Track jog state and throttle updates via requestAnimationFrame
let jogRaf = null;
let jogSpeed = 1;
let jogDirection = 1;
let jogging = false;
let isSeeking = false;
// Track whether template details are shown. Expose on window so inline
// scripts and other modules can share this state.
window.detailsVisible = false;
// Throttle duplicate error messages so the overlay isn't spammed when
// a camera repeatedly fails. Track the last message and time displayed.
let lastErrorMessage = "";
let lastErrorTime = 0;

function setOverlayState(kind, message = "") {
  const isLoading = kind === "loading";
  const isOffline = kind === "offline";
  const isCaptureError = kind === "capture-error";
  const isStreamError = kind === "stream-error";

  loadingIndicator.style.display = isLoading ? "block" : "none";
  playPauseIndicator.style.display = "none";

  offlineIndicator.style.display = isOffline ? "block" : "none";
  offlineMessage.textContent = isOffline ? message : "";

  errorIndicator.style.display = isCaptureError ? "block" : "none";
  errorIndicatorMessage.textContent = isCaptureError ? message : "";

  streamErrorIndicator.style.display = isStreamError ? "block" : "none";
  streamErrorMessage.textContent = isStreamError ? message : "";

  const shouldShowOverlay =
    isLoading || isOffline || isCaptureError || isStreamError;
  videoOverlay.style.display = shouldShowOverlay ? "block" : "none";
}

function updateCameraOptions(group) {
  const camSelect = document.getElementById("camera-selector");
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
  Object.entries(templateDetails)
    .filter(
      ([cam, det]) =>
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

function changeGroup(group) {
  const navGroup = document.getElementById("nav-group-dropdown");
  if (!group) {
    group = navGroup ? navGroup.value : "all";
  }
  if (navGroup) navGroup.value = group;
  updateCameraOptions(group);
  changeCamera(group === "all" ? "All" : `group-${group}`);
}

// Restore previously selected camera, source and speed from localStorage so
// reloading the page keeps user preferences. If the user specified a camera in
// the URL query string that takes precedence.
function loadSavedPreferences() {
  if (!requestedCamera) {
    const savedCam = localStorage.getItem("liveCamera");
    const camSelect = document.getElementById("camera-selector");
    const navGroup = document.getElementById("nav-group-dropdown");
    if (
      savedCam &&
      camSelect &&
      camSelect.querySelector(`option[value="${savedCam}"]`)
    ) {
      currentCamera = savedCam;
      camSelect.value = savedCam;
    }
    if (navGroup) {
      if (currentCamera === "All") {
        navGroup.value = "all";
      } else if (currentCamera.startsWith("group-")) {
        navGroup.value = currentCamera.split("group-")[1];
      }
      updateCameraOptions(navGroup.value);
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
  video.pause();
  video.removeAttribute("src");
}

function showLoadingIndicator() {
  setOverlayState("loading");
}

function hideLoadingIndicator() {
  loadingIndicator.style.display = "none";
  if (videoOverlay.style.display === "block") {
    setTimeout(() => {
      const hasActiveStatus =
        offlineIndicator.style.display !== "none" ||
        errorIndicator.style.display !== "none" ||
        streamErrorIndicator.style.display !== "none";
      if (!hasActiveStatus && playPauseIndicator.style.display === "none") {
        videoOverlay.style.display = "none";
      }
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
  const now = Date.now();
  if (message === lastErrorMessage && now - lastErrorTime < 10000) {
    return;
  }
  lastErrorMessage = message;
  lastErrorTime = now;

  errorMessage.textContent = message;
  errorMessage.style.display = "block";
  showStreamErrorIndicator(message);
  setTimeout(() => {
    errorMessage.style.display = "none";
  }, 5000);
}

function showOfflineIndicator(message) {
  setOverlayState("offline", message);
}

function hideOfflineIndicator() {
  if (offlineIndicator.style.display !== "none") {
    setOverlayState("none");
  }
}

function showCaptureErrorIndicator(cameraName) {
  setOverlayState("capture-error", `Capture failed for ${cameraName}`);
}

function hideCaptureErrorIndicator() {
  if (errorIndicator.style.display !== "none") {
    setOverlayState("none");
  }
}

function showStreamErrorIndicator(message) {
  setOverlayState("stream-error", message);
}

function hideStreamErrorIndicator() {
  if (streamErrorIndicator.style.display !== "none") {
    setOverlayState("none");
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
image.addEventListener("load", () => {
  // When switching cameras/groups, we first show a still "last good" frame to
  // avoid a blank player. Keep the spinner visible until the actual stream
  // produces a frame.
  if (image.dataset.mode === "snapshot") return;
  hideLoadingIndicator();
});
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

function changeCamera(selectedValue) {
  showLoadingIndicator();
  if (!selectedValue) {
    const cameraSelector = document.getElementById("camera-selector");
    if (cameraSelector) {
      selectedValue = cameraSelector.value;
    } else {
      const navGroup = document.getElementById("nav-group-dropdown");
      if (navGroup && navGroup.value !== "all") {
        selectedValue = `group-${navGroup.value}`;
      } else {
        selectedValue = "All";
      }
    }
  }
  // Check if the camera is connected
  let isConnected = checkCameraConnection(currentCamera);

  if (selectedValue === "All") {
    // Handle the "All" option separately
    currentCamera = "All";
    templateDetails["All"] = {
      url: "/stream.mp4", // Set the URL for the MP4 stream without a group
      groupCameras: getCameraNames(), // Add all cameras but skip groups
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

  const navGroup = document.getElementById("nav-group-dropdown");
  if (navGroup) {
    if (selectedValue === "All") {
      navGroup.value = "all";
    } else if (selectedValue.startsWith("group-")) {
      navGroup.value = selectedValue.split("group-")[1];
    } else {
      navGroup.value = "";
    }
  }

  // Persist the chosen camera so the selection sticks across sessions
  localStorage.setItem("liveCamera", currentCamera);

  if (!isConnected) {
    showOfflineIndicator(`Camera ${currentCamera} is currently offline`);
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
  if (!window.detailsVisible) {
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
  image.title = details.last_caption;
  templateDetailsContainer.style.display = "block";
  templateDetailsContainer.innerHTML = `
        <div>
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
    showOfflineIndicator(`Camera ${currentCamera} is currently offline`);
    hideCaptureErrorIndicator();
    hideLoadingIndicator();
    video.pause();
    video.src = "";
    showLastScreenshot();
    updateSeekBar();
    updateJogShuttle();
    return;
  } else if (details && details.capture_failed) {
    hideOfflineIndicator();
    showCaptureErrorIndicator(currentCamera);
    hideLoadingIndicator();
    video.pause();
    video.src = "";
    showLastScreenshot();
    updateSeekBar();
    updateJogShuttle();
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
  updateJogShuttle();
}

function playM3U8() {
  resetVideo();
  video.style.display = "block";
  // HLS streams are live and not seekable
  const seekBar = document.getElementById("seek-bar");
  if (seekBar) {
    seekBar.style.display = "none";
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
      safePlay(video);
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
      safePlay(video);
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
      groupCameras = getCameraNames().filter(Boolean);
    } else {
      // If a specific group is selected, get the cameras in that group
      const groupName = currentCamera.split("group-")[1];
      const groupDetails = templateDetails["group-" + groupName];
      if (groupDetails) {
        groupCameras = (groupDetails.groupCameras || []).filter(Boolean);
      } else {
        // Fallback: collect cameras belonging to the group on the fly
        groupCameras = Object.entries(templateDetails)
          .filter(
            ([camera, details]) =>
              details.groups &&
              details.groups
                .split(",")
                .map((s) => s.trim())
                .includes(groupName),
          )
          .map(([camera]) => camera)
          .filter(Boolean);
      }
    }

    if (!groupCameras || groupCameras.length === 0) {
      console.warn("playLoop: no cameras available for", currentCamera);
      showError("No cameras available for loop");
      showLastScreenshot();
      return;
    }

    let cameraIndex = 0;

    loopHandler = () => {
      if (cameraIndex >= groupCameras.length) {
        cameraIndex = 0; // Reset the index to loop through the cameras again
      }
      const cameraName = groupCameras[cameraIndex];
      setClipSrc(cameraName);
      cameraIndex++; // Move to the next camera
    };

    loopHandler(); // Start the loop
    video.addEventListener("ended", loopHandler); // Continue the loop when the video ends
  } else {
    // Handling for individual cameras
    setClipSrc(currentCamera);
  }
}

function updateFrameTimestamp() {
  updateFrameTimestampUtil(templateDetails, currentCamera);
}

function setTimestampVisibility(show) {
  setTimestampVisibilityUtil(templateDetails, currentCamera, show);
}

function refreshPNG() {
  image.dataset.mode = "png";
  image.src =
    "/last_screenshot/" +
    encodeURIComponent(currentCamera) +
    "?time=" +
    new Date().getTime();
  updateFrameTimestamp();
}

function showLastScreenshot() {
  let url;
  if (currentCamera === "All") {
    // Show the most recent screenshot across all cameras
    url = "/stream.png?time=" + new Date().getTime();
  } else if (currentCamera.startsWith("group-")) {
    // Group views use a dedicated group screenshot generated server-side.
    const groupName = currentCamera.split("group-")[1];
    url = `/stream.png?group=${encodeURIComponent(groupName)}&time=${new Date().getTime()}`;
  } else {
    // Display the latest screenshot for the selected camera
    url = `/stream.png?camera=${encodeURIComponent(currentCamera)}&time=${new Date().getTime()}`;
  }

  // Preload the image so the viewer always sees a frame when switching
  const pre = new Image();
  pre.onload = () => {
    image.dataset.mode = "snapshot";
    image.src = pre.src;
  };
  // If the snapshot isn't available yet (404/timeout), keep showing the prior
  // frame and keep the spinner visible while the stream connects.
  pre.onerror = () => {};
  pre.src = url;
  image.style.display = "block";
  updateFrameTimestamp();
}

function playMP4() {
  resetVideo();
  video.style.display = "block";
  stopLiveSwitch();
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
  safePlay(video);

  // Remove any existing 'ended' event listeners
  video.removeEventListener("ended", handleVideoEnded);

  // Add an event listener for the 'ended' event
  video.addEventListener("ended", handleVideoEnded);
}

function handleVideoEnded() {
  if (currentCamera === "All" || currentCamera.startsWith("group-")) {
    // For "All" or group options, move to the next camera
    const groupCameras = (
      templateDetails[currentCamera].groupCameras || []
    ).filter(Boolean);
    const currentIndex = groupCameras.indexOf(video.dataset.currentCamera);
    const nextIndex = (currentIndex + 1) % groupCameras.length;
    const nextCamera = groupCameras[nextIndex];
    setClipSrc(nextCamera);
    video.dataset.currentCamera = nextCamera;
  }
}

function playLive() {
  resetVideo();
  showLoadingIndicator();
  video.style.display = "block";
  // Live video cannot be scrubbed
  const seekBar = document.getElementById("seek-bar");
  if (seekBar) {
    seekBar.style.display = "none";
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
      groupCameras = getCameraNames();
    } else {
      const groupName = currentCamera.split("group-")[1];
      const groupDetails = templateDetails["group-" + groupName];
      if (groupDetails) {
        groupCameras = groupDetails.groupCameras;
      } else {
        // Fallback: collect cameras belonging to the group on the fly
        groupCameras = Object.entries(templateDetails)
          .filter(
            ([camera, details]) =>
              details.groups &&
              details.groups
                .split(",")
                .map((s) => s.trim())
                .includes(groupName),
          )
          .map(([camera]) => camera);
      }
    }

    if (!groupCameras || groupCameras.length === 0) {
      console.warn("playLive: no cameras available for", currentCamera);
      showError("No cameras available for live view");
      showLastScreenshot();
      return;
    }

    let cameraIndex = 0;
    liveSwitchFunction = () => {
      if (cameraIndex >= groupCameras.length) {
        cameraIndex = 0;
      }
      const cameraName = groupCameras[cameraIndex];
      video.src = "/live_video?camera=" + encodeURIComponent(cameraName);
      video.load();
      safePlay(video);
      cameraIndex++;
    };

    const slider = document.getElementById("speed-slider");
    const secs = Math.max(1, parseInt(slider.value, 10) || 1);
    liveSwitchFunction();
    liveSwitchInterval = setInterval(liveSwitchFunction, secs * 1000);
  } else {
    video.src = "/live_video?camera=" + encodeURIComponent(currentCamera);
    video.load();
    safePlay(video);
  }
}

function playPNG() {
  // When switching from video playback to PNG images, ensure any
  // ongoing video stream is stopped to avoid "media element" errors.
  resetVideo();
  stopPNG();
  video.pause();
  video.src = "";
  stopLiveSwitch();
  stopPNG();
  video.style.display = "none";
  image.style.display = "block";
  const slider = document.getElementById("speed-slider");
  const secs = Math.max(1, parseInt(slider.value, 10) || 1);
  const seekBar = document.getElementById("seek-bar");
  if (seekBar) {
    seekBar.style.display = "none";
    seekBar.style.pointerEvents = "none";
    seekBar.disabled = true;
  }
  // Structured log for easier scraping by Grafana Loki
  console.info(
    JSON.stringify({
      ts: Date.now(),
      ctx: "discover",
      msg: `seekBar:${seekBar},secs:${secs}`,
    }),
  );
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
    pngInterval = setInterval(refreshGroupPNG, secs * 1000);
  } else if (currentCamera === "All") {
    // Special handling for the "All" option
    let cameraIndex = 0;
    const allCameras = getCameraNames().filter(Boolean);
    const refreshAllPNG = () => {
      if (cameraIndex >= allCameras.length) {
        cameraIndex = 0;
      }
      const cameraName = allCameras[cameraIndex];
      image.src =
        "/last_screenshot/" + cameraName + "?time=" + new Date().getTime();
      cameraIndex++;
    };
    refreshAllPNG();
    clearInterval(pngInterval);
    pngInterval = setInterval(refreshAllPNG, secs * 1000);
  } else {
    // Original behavior for individual cameras
    refreshPNG();
    clearInterval(pngInterval);
    pngInterval = setInterval(refreshPNG, secs * 1000);
  }
}

function playMJPG() {
  // Stop any existing video stream before showing MJPEG frames
  resetVideo();
  stopPNG();
  video.pause();
  video.src = "";
  stopLiveSwitch();
  stopPNG();
  video.style.display = "none";
  image.style.display = "block";
  image.dataset.mode = "mjpg";
  // MJPEG streams are continuous images, disable scrubbing
  const seekBar = document.getElementById("seek-bar");
  if (seekBar) {
    seekBar.style.display = "none";
    seekBar.style.pointerEvents = "none";
    seekBar.disabled = true;
  }
  stopLiveSwitch();
  stopPNG();
  const ts = Date.now();
  if (currentCamera.startsWith("group-")) {
    // Special handling for groups
    const groupName = currentCamera.split("group-")[1];
    image.src = `/stream.mjpg?group=${encodeURIComponent(groupName)}&time=${ts}`;
  } else if (currentCamera === "All") {
    // Special handling for the "All" option
    image.src = `/stream.mjpg?group=all&time=${ts}`;
  } else {
    // URL for individual cameras
    image.src = `/fast_stream.mjpg?camera=${encodeURIComponent(currentCamera)}&time=${ts}`;
  }
}

function playMotion() {
  // Stop any existing video stream before showing motion JPEG frames
  resetVideo();
  stopPNG();
  video.pause();
  video.src = "";
  stopLiveSwitch();
  stopPNG();
  video.style.display = "none";
  image.style.display = "block";
  image.dataset.mode = "motion";
  const seekBar = document.getElementById("seek-bar");
  if (seekBar) {
    seekBar.style.display = "none";
    seekBar.style.pointerEvents = "none";
    seekBar.disabled = true;
  }
  stopLiveSwitch();
  stopPNG();
  const ts = Date.now();
  if (currentCamera.startsWith("group-")) {
    // Special handling for groups
    const groupName = currentCamera.split("group-")[1];
    image.src = `/motion.mjpg?group=${encodeURIComponent(groupName)}&time=${ts}`;
  } else if (currentCamera === "All") {
    // Special handling for the "All" option
    image.src = `/motion.mjpg?group=all&time=${ts}`;
  } else {
    // URL for individual cameras
    image.src = `/motion.mjpg?camera=${encodeURIComponent(currentCamera)}&time=${ts}`;
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
  const secs = Math.max(1, parseInt(slider.value, 10) || 1);
  localStorage.setItem("playbackSpeed", slider.value);
  const fps = 1 / secs;
  video.playbackRate = fps;
  speedDisplay.textContent = secs === 60 ? "1fpm" : `${fps.toFixed(2)}fps`;

  // Adjust the refresh rate for the PNG stream based on the playback speed
  if (pngInterval) {
    clearInterval(pngInterval);
    pngInterval = setInterval(refreshPNG, secs * 1000);
  }

  // Adjust the live group switch interval if active
  if (liveSwitchInterval && liveSwitchFunction) {
    clearInterval(liveSwitchInterval);
    liveSwitchInterval = setInterval(liveSwitchFunction, secs * 1000);
  }

  speedDisplay.classList.add("highlight-speed");
  setTimeout(() => speedDisplay.classList.remove("highlight-speed"), 500);
}

function stopPNG() {
  if (pngInterval) {
    clearInterval(pngInterval);
    pngInterval = null;
  }
  // Hide the image and clear the source so browsers don't briefly
  // display the broken image icon when switching cameras.
  image.style.display = "none";
  image.removeAttribute("src");
}

function stopLiveSwitch() {
  if (liveSwitchInterval) {
    clearInterval(liveSwitchInterval);
    liveSwitchInterval = null;
    liveSwitchFunction = null;
  }
}

function scheduleJogUpdate() {
  if (!jogRaf) {
    jogRaf = requestAnimationFrame(() => {
      if (jogDirection < 0) {
        video.currentTime = Math.max(0, video.currentTime - 0.05 * jogSpeed);
      } else {
        video.playbackRate = jogSpeed;
      }
      jogRaf = null;
    });
  }
}

function handleJogMove(e) {
  if (!jogging) return;
  const rect = jogShuttle.getBoundingClientRect();
  const x = e.clientX - rect.left - rect.width / 2;
  const radius = rect.width / 2;
  const norm = Math.max(-1, Math.min(1, x / radius));
  const level = Math.min(4, Math.floor(Math.abs(norm) * 4));
  jogSpeed = Math.pow(2, level);
  if (jogSpeed === 0) return;
  jogDirection = Math.sign(norm);
  scheduleJogUpdate();
}

function stopJog() {
  if (!jogging) return;
  jogging = false;
  if (jogRaf) {
    cancelAnimationFrame(jogRaf);
    jogRaf = null;
  }
  if (jogDirection >= 0) {
    video.playbackRate = jogSpeed;
    safePlay(video);
  } else {
    video.pause();
  }
}

function initJogShuttle() {
  if (!jogShuttle) return;
  jogShuttle.addEventListener("mousedown", (e) => {
    jogging = true;
    video.pause();
    handleJogMove(e);
  });
  jogShuttle.addEventListener("touchstart", (e) => {
    jogging = true;
    video.pause();
    handleJogMove(e.touches[0]);
  });
  window.addEventListener("touchmove", (e) => {
    handleJogMove(e.touches[0]);
  });
  window.addEventListener("touchend", stopJog);
  window.addEventListener("mousemove", handleJogMove);
  window.addEventListener("mouseup", stopJog);
}

function updateSpeedContainer() {
  if (!speedContainer) return;
  const source = document.getElementById("video-source").value;
  const isGroupView =
    currentCamera === "All" || currentCamera.startsWith("group-");
  let cameraCount = 0;
  if (isGroupView) {
    if (currentCamera === "All") {
      cameraCount = getCameraNames().length;
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
  if (controlsWrapper) {
    controlsWrapper.style.display = show ? "block" : "none";
  }
}

function updateSeekBar() {
  const seekBar = document.getElementById("seek-bar");
  if (!seekBar) return;
  const source = document.getElementById("video-source").value;
  const isSingleCamera = !(
    currentCamera === "All" || currentCamera.startsWith("group-")
  );
  const show = isSingleCamera && (source === "mp4" || source === "loop");
  seekBar.style.display = show ? "block" : "none";
  seekBar.style.pointerEvents = show ? "auto" : "none";
  seekBar.disabled = !show;
  if (show) {
    seekBar.max = video.duration || 0;
    seekBar.value = video.currentTime || 0;
  }
  setTimestampVisibility(show);
}

function updateJogShuttle() {
  if (!jogShuttle) return;
  const source = document.getElementById("video-source").value;
  const isSingleCamera = !(
    currentCamera === "All" || currentCamera.startsWith("group-")
  );
  const show = isSingleCamera && (source === "mp4" || source === "loop");
  jogShuttle.style.visibility = show ? "visible" : "hidden";
  jogShuttle.style.pointerEvents = show ? "auto" : "none";
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

  const lastScreenshotTime = parseTimestamp(camera.last_screenshot_time);
  if (!lastScreenshotTime) {
    return false;
  }
  const oneHourAgo = new Date(Date.now() - 60 * 60 * 1000);
  return lastScreenshotTime > oneHourAgo;
}

let captionInterval;

async function fetchLatestCaptions() {
  try {
    const resp = await fetch("/templates");
    if (!resp.ok) return;
    const data = await resp.json();
    if (data.error === "unauthorized") {
      const ok = await attemptAutoLogin();
      if (ok) {
        fetchLatestCaptions();
      }
      return;
    }
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
updateJogShuttle();
initJogShuttle();
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
      safePlay(video);
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
    window.detailsVisible = !window.detailsVisible;
    updateTemplateDetails();
  });
}

function togglePlayback() {
  if (video.paused) {
    safePlay(video);
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
    event.target.tagName === "TEXTAREA" ||
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
window.changeGroup = changeGroup;
window.updateCameraOptions = updateCameraOptions;

if (playButton) {
  playButton.addEventListener("click", togglePlayback);
}

// --- Offline handling ---
let reconnectTimer = null;
let resumeTime = 0;
let wasPlaying = false;

async function attemptReconnect() {
  try {
    const res = await fetch("/network_status");
    const data = await res.json();
    if (data.error === "unauthorized") {
      const ok = await attemptAutoLogin();
      if (ok) {
        return attemptReconnect();
      }
      return;
    }
    if (data.online) {
      clearInterval(reconnectTimer);
      reconnectTimer = null;
      hideOfflineIndicator();
      video.currentTime = resumeTime;
      if (wasPlaying) {
        safePlay(video);
      }
    }
  } catch {
    // still offline
  }
}

function handleNetworkOffline() {
  wasPlaying = !video.paused;
  resumeTime = video.currentTime;
  video.pause();
  showOfflineIndicator("Offline. Reconnecting...");
  if (!reconnectTimer) {
    reconnectTimer = setInterval(attemptReconnect, 5000);
  }
}

async function handleNetworkOnline() {
  await attemptReconnect();
}

window.addEventListener("offline", handleNetworkOffline);
window.addEventListener("online", handleNetworkOnline);

// Allow pausing/resuming the video by clicking anywhere on the player
video.addEventListener("click", togglePlayback);

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

export {
  updateFrameTimestamp,
  getCameraNames,
  handleNetworkOffline,
  handleNetworkOnline,
  setClipSrc,
};
