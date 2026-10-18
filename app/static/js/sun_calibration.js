const state = {
  cameras: [],
  activeCamera: null,
};

const cameraList = document.getElementById("sun-camera-list");
const cameraFilter = document.getElementById("sun-camera-filter");
const frameList = document.getElementById("sun-frame-list");
const activeTitle = document.getElementById("sun-active-title");
const activeMeta = document.getElementById("sun-active-meta");
const fovInput = document.getElementById("sun-fov");
const queueList = document.getElementById("sun-queue-list");
const refreshQueueButton = document.getElementById("sun-refresh-queue");

function text(value) {
  return value === null || value === undefined || value === ""
    ? "unknown"
    : String(value);
}

function cameraMatchesFilter(camera, query) {
  if (!query) return true;
  const haystack = [
    camera.name,
    camera.location_label,
    camera.current_direction,
    ...(camera.groups || []),
  ]
    .join(" ")
    .toLowerCase();
  return haystack.includes(query.toLowerCase());
}

function renderCameras() {
  const query = cameraFilter.value.trim();
  cameraList.innerHTML = "";
  const cameras = state.cameras.filter((camera) =>
    cameraMatchesFilter(camera, query),
  );

  if (!cameras.length) {
    cameraList.innerHTML =
      '<div class="sun-empty-state">No matching cameras.</div>';
    return;
  }

  for (const camera of cameras) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "sun-camera-card";
    button.disabled = !camera.calibration_candidate;
    if (state.activeCamera?.name === camera.name) {
      button.classList.add("is-active");
    }

    const bearing = camera.current_bearing_degrees;
    const pose =
      bearing === null || bearing === undefined
        ? text(camera.current_direction)
        : `${Number(bearing).toFixed(1)} deg ${text(camera.current_direction)}`;
    button.innerHTML = `
      <div class="sun-camera-name">${camera.name}</div>
      <div class="sun-camera-meta">${text(camera.location_label)}</div>
      <div class="sun-camera-meta">${camera.frame_count} frames | pose ${pose}</div>
      <div class="sun-camera-meta">${text(camera.calibration_reason)}</div>
    `;
    button.addEventListener("click", () => selectCamera(camera.name));
    cameraList.appendChild(button);
  }
}

function renderQueue(queue) {
  if (!queueList) return;
  queueList.innerHTML = "";
  if (!queue.length) {
    queueList.innerHTML =
      '<div class="sun-empty-state">No outdoor cameras are ready for sun calibration yet.</div>';
    return;
  }

  for (const item of queue) {
    const camera = item.camera;
    const frame = item.best_frame;
    const status = item.status || {};
    const button = document.createElement("button");
    button.type = "button";
    button.className = "sun-queue-card";
    if (state.activeCamera?.name === camera.name) {
      button.classList.add("is-active");
    }
    const bearing = camera.current_bearing_degrees;
    const pose =
      bearing === null || bearing === undefined
        ? text(camera.current_direction)
        : `${Number(bearing).toFixed(1)} deg ${text(camera.current_direction)}`;
    const imageHtml = frame?.image_url
      ? `<img src="${frame.image_url}" loading="lazy" alt="${camera.name} best calibration frame" />`
      : '<div class="sun-empty-state">No frame</div>';
    const score = frame ? `score ${frame.score}` : "no score";
    const sun = frame
      ? `${frame.sun_cardinal} sun ${Number(frame.sun_elevation_degrees).toFixed(1)} deg`
      : "no sun frame";
    button.innerHTML = `
      ${imageHtml}
      <div class="sun-queue-body">
        <div class="sun-camera-name">${camera.name}</div>
        <div class="sun-queue-badges">
          <span class="sun-queue-badge ${status.key || ""}">${text(status.label)}</span>
          <span class="sun-queue-badge">${score}</span>
        </div>
        <div class="sun-camera-meta">${sun}</div>
        <div class="sun-camera-meta">pose ${pose}</div>
      </div>
    `;
    button.addEventListener("click", () => selectCamera(camera.name));
    queueList.appendChild(button);
  }
}

async function loadQueue() {
  if (!queueList) return;
  queueList.innerHTML =
    '<div class="sun-empty-state">Ranking calibration queue...</div>';
  const response = await fetch(
    "/api/sun-calibration/queue?history_limit=1500",
    {
      credentials: "same-origin",
    },
  );
  const payload = await response.json();
  if (!response.ok) {
    queueList.innerHTML = `<div class="sun-empty-state">Unable to load queue: ${payload.error || response.status}</div>`;
    return;
  }
  renderQueue(payload.queue || []);
}

function framePositionLabel(position) {
  return {
    left_edge: "Left edge",
    left_third: "Left",
    center: "Center",
    right_third: "Right",
    right_edge: "Right edge",
  }[position];
}

async function saveBearing(camera, frame, position, card) {
  const result = card.querySelector(".sun-save-result");
  const note = card.querySelector(".sun-note")?.value || "";
  result.textContent = "Saving...";

  const response = await fetch(
    `/api/sun-calibration/${encodeURIComponent(camera.name)}/bearing`,
    {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        filename: frame.filename,
        frame_position: position,
        horizontal_fov_degrees: Number(
          fovInput.value || camera.horizontal_fov_degrees || 90,
        ),
        note,
      }),
    },
  );
  const payload = await response.json();
  if (!response.ok || !payload.ok) {
    result.textContent = `Save failed: ${payload.error || response.status}`;
    return;
  }

  result.textContent = `Saved ${payload.direction} / ${Number(payload.bearing_degrees).toFixed(1)} deg`;
  state.activeCamera.current_bearing_degrees = payload.bearing_degrees;
  state.activeCamera.current_direction = payload.direction;
  state.activeCamera.pose_confidence = "operator";
  renderCameras();
  loadQueue();
}

function renderFrames(camera, frames) {
  frameList.innerHTML = "";
  if (!frames.length) {
    frameList.innerHTML =
      '<div class="sun-empty-state">No canonical history frames found for this camera.</div>';
    return;
  }

  for (const frame of frames) {
    const card = document.createElement("article");
    card.className = "sun-frame-card";
    card.innerHTML = `
      <img src="${frame.image_url}" loading="lazy" alt="${camera.name} frame ${frame.captured_at}" />
      <div class="sun-frame-body">
        <div class="sun-frame-title">
          <span>${frame.sun_cardinal} sun</span>
          <span class="sun-score">score ${frame.score}</span>
        </div>
        <div class="sun-frame-meta">
          ${frame.captured_at}<br />
          azimuth ${Number(frame.sun_azimuth_degrees).toFixed(1)} deg,
          elevation ${Number(frame.sun_elevation_degrees).toFixed(1)} deg
        </div>
        <textarea class="sun-note" placeholder="Optional note: glare on right window, shadows point toward camera, etc."></textarea>
        <div class="sun-position-buttons" aria-label="Where is the sun in this frame?"></div>
        <div class="sun-save-result" aria-live="polite"></div>
      </div>
    `;
    const buttonRow = card.querySelector(".sun-position-buttons");
    for (const position of [
      "left_edge",
      "left_third",
      "center",
      "right_third",
      "right_edge",
    ]) {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = framePositionLabel(position);
      button.addEventListener("click", () =>
        saveBearing(camera, frame, position, card),
      );
      buttonRow.appendChild(button);
    }
    frameList.appendChild(card);
  }
}

async function selectCamera(name) {
  const camera = state.cameras.find((item) => item.name === name);
  if (!camera || !camera.has_location) return;

  state.activeCamera = camera;
  activeTitle.textContent = camera.name;
  activeMeta.textContent = `${text(camera.location_label)} | ${camera.frame_count} frames | current ${text(camera.current_direction)}`;
  fovInput.value = Number(camera.horizontal_fov_degrees || 90).toFixed(0);
  frameList.innerHTML =
    '<div class="sun-empty-state">Scoring history frames...</div>';
  renderCameras();
  loadQueue();

  const response = await fetch(
    `/api/sun-calibration/${encodeURIComponent(name)}/frames?limit=72`,
    {
      credentials: "same-origin",
    },
  );
  const payload = await response.json();
  if (!response.ok) {
    frameList.innerHTML = `<div class="sun-empty-state">Unable to load frames: ${payload.error || response.status}</div>`;
    return;
  }
  renderFrames(payload.camera, payload.frames);
}

async function loadCameras() {
  cameraList.innerHTML =
    '<div class="sun-empty-state">Loading cameras...</div>';
  const response = await fetch("/api/sun-calibration/cameras", {
    credentials: "same-origin",
  });
  const payload = await response.json();
  state.cameras = payload.cameras || [];
  renderCameras();
  loadQueue();

  const firstReady = state.cameras.find(
    (camera) => camera.calibration_candidate,
  );
  if (firstReady) {
    selectCamera(firstReady.name);
  }
}

cameraFilter?.addEventListener("input", renderCameras);
refreshQueueButton?.addEventListener("click", loadQueue);
loadCameras().catch((error) => {
  cameraList.innerHTML = `<div class="sun-empty-state">Failed to load cameras: ${error}</div>`;
});
