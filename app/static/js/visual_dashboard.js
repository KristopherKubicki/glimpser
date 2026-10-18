import { presentationValue } from "./presentation_config.js";
import { mountAmbientClock } from "./ambient_clock.js";
import {
  captionAge,
  safeMediaUrl,
  captureImageUrl,
  captureAge,
  sourceAge,
  sourceNeedsAttention,
} from "./capture_age.js";
import { mountMotionPreview } from "./motion_preview.js?v=20261017-media-lifecycle";
import {
  livePilotEligible,
  liveStreamLimit,
  mountKioskLive,
} from "./kiosk_live.js?v=20261017-media-lifecycle";

const HOUSE_BOARD_ORDER = {
  [presentationValue("StoreOne arrivals")]: [
    "Front_door_doorbell",
    presentationValue("StoreOne200"),
    presentationValue("StoreOneEntryFisheye"),
    "Showroom_Entrance",
  ],
  [presentationValue("Home property health")]: [
    "Backyard",
    "Garden",
    "Driveway",
    "Garage",
    "Walkway",
  ],
  [presentationValue("Home arrivals")]: [
    "FrontDoor",
    "Driveway",
    "Garage",
    "Walkway",
    "Street",
    "Backyard",
    "Garden",
  ],
  "Beach property health": [
    "BeachSouthJetty",
    "BeachShore",
    "BeachMapleTree",
    "BeachDriveway",
    "BeachPathway",
    "BeachFrontYard",
  ],
  "Beach arrivals": ["BeachDriveway", "BeachPathway", "BeachFrontYard"],
  Approaches: ["FrontDoor", "Driveway", "Street"],
  "Around the home": ["Backyard", "Garden", "Garage", "Walkway"],
};
const PROPERTY_SIGNALS = [
  ["HubitatWaterPumpsFlood", "Water & pumps"],
  ["HubitatPower", "Power"],
  ["HubitatHVAC", "Climate"],
];
const BEACH_PROPERTY_SIGNALS = [["HubitatBeachMain", "Beach house status"]];

export function selectPropertySignals(
  cameras,
  group = presentationValue("Home property health"),
) {
  const byName = new Map(cameras.map((camera) => [camera.name, camera]));
  const signals =
    group === "Beach property health"
      ? BEACH_PROPERTY_SIGNALS
      : PROPERTY_SIGNALS;
  return signals.map(([name, label]) => ({
    name,
    label,
    camera: byName.get(name) || null,
  }));
}

const motionTime = (camera) => {
  const raw = camera.motion_at || "";
  return Date.parse(
    /(?:Z|[+-]\d{2}:?\d{2})$/i.test(raw) ? raw : `${raw.replace(" ", "T")}Z`,
  );
};
const hasRecentMotion = (camera, now) => {
  const age = now - motionTime(camera);
  return age >= 0 && age <= 5 * 60000;
};
const HOME_ROTATING_GROUPS = new Set([
  presentationValue("Home property health"),
  presentationValue("Home arrivals"),
]);

export function selectBoardCameras(cameras, group, rotation = 0, now = 0) {
  const order = HOUSE_BOARD_ORDER[group];
  if (!order) return cameras.slice(0, 6);
  const sorted = [...cameras].sort((a, b) => {
    const ai = order.indexOf(a.name);
    const bi = order.indexOf(b.name);
    return (ai < 0 ? order.length : ai) - (bi < 0 ? order.length : bi);
  });
  if (!HOME_ROTATING_GROUPS.has(group) || sorted.length <= 4)
    return sorted.slice(0, 4);
  const anchor =
    group === presentationValue("Home arrivals")
      ? sorted.find((c) => c.name === "FrontDoor")
      : null;
  const cycling = anchor
    ? sorted.filter((camera) => camera !== anchor)
    : sorted;
  const offset = rotation % cycling.length;
  const rotated = [...cycling.slice(offset), ...cycling.slice(0, offset)];
  const recentMotion = cycling
    .filter((camera) => hasRecentMotion(camera, now))
    .sort((a, b) => motionTime(b) - motionTime(a));
  return [
    ...(anchor ? [anchor] : []),
    ...recentMotion,
    ...rotated.filter((camera) => !recentMotion.includes(camera)),
  ].slice(0, 4);
}

export function selectBoardLive(
  records,
  group,
  rotation = 0,
  now = Date.now(),
  device = globalThis.navigator,
) {
  const motion = HOME_ROTATING_GROUPS.has(group)
    ? records
        .filter((record) => hasRecentMotion(record.camera, now))
        .sort((a, b) => motionTime(b.camera) - motionTime(a.camera))[0]
    : null;
  const door =
    group === presentationValue("Home arrivals")
      ? records.find((record) => record.camera.name === "FrontDoor")
      : null;
  const pinned = [...new Set([door, motion].filter(Boolean))].slice(0, 2);
  const others = records.filter((record) => !pinned.includes(record));
  const offset = others.length ? rotation % others.length : 0;
  return [...pinned, ...others.slice(offset), ...others.slice(0, offset)].slice(
    0,
    liveStreamLimit(device),
  );
}

export function selectBoardCandidates(members, group) {
  const healthy = members.filter(
    (camera) => !camera.issue && !sourceNeedsAttention(camera.freshness),
  );
  if (!healthy.length) return members;
  if (group !== presentationValue("Home arrivals")) return healthy;
  const door = members.find((camera) => camera.name === "FrontDoor");
  return door && !healthy.includes(door) ? [...healthy, door] : healthy;
}

const el = (tag, className, text) => {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
};
const svgEl = (tag, attrs) => {
  const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
  Object.entries(attrs).forEach(([key, value]) =>
    node.setAttribute(key, value),
  );
  return node;
};
export function projectLocations(cameras) {
  const located = cameras.filter((c) => c.location);
  if (!located.length) return [];
  const centerLat =
    located.reduce((sum, c) => sum + c.location.lat, 0) / located.length;
  const scaleX = Math.cos((centerLat * Math.PI) / 180);
  const points = located.map((c) => ({
    camera: c,
    x: c.location.lon * scaleX,
    y: -c.location.lat,
  }));
  const xs = points.map((p) => p.x),
    ys = points.map((p) => p.y);
  const minX = Math.min(...xs),
    maxX = Math.max(...xs),
    minY = Math.min(...ys),
    maxY = Math.max(...ys);
  const scale = Math.min(
    420 / Math.max(maxX - minX, 0.01),
    210 / Math.max(maxY - minY, 0.01),
  );
  return points.map((p) => ({
    camera: p.camera,
    x: 250 + (p.x - (minX + maxX) / 2) * scale,
    y: 140 + (p.y - (minY + maxY) / 2) * scale,
  }));
}
// A failed still must not leave a broken image or an indefinite loading panel.
export function createDetailCapture(camera) {
  const node = el("div", "vd-detail-capture");
  const image = el("img", "vd-detail-image");
  image.alt = `${camera.name} saved capture`;
  image.hidden = true;
  const status = el("p", "vd-capture-status", "Loading saved capture…");
  status.setAttribute("role", "status");
  node.append(image, status);
  let settled = false;
  const clear = () => {
    window.clearTimeout(timeout);
    image.onload = null;
    image.onerror = null;
  };
  const fail = () => {
    if (settled) return;
    settled = true;
    clear();
    image.removeAttribute("src");
    status.textContent =
      "Saved capture unavailable. You can still try the camera player or a recent replay.";
    node.classList.add("is-unavailable");
  };
  const timeout = window.setTimeout(fail, 10000);
  image.onload = () => {
    if (settled) return;
    settled = true;
    clear();
    status.hidden = true;
    image.hidden = false;
    node.classList.add("is-ready");
  };
  image.onerror = fail;
  image.src = captureImageUrl(camera.image, camera.captured);
  return {
    node,
    dispose() {
      settled = true;
      clear();
      image.removeAttribute("src");
    },
  };
}

export function initVisualDashboard() {
  const root = document.querySelector("[data-visual-dashboard]");
  if (!root) return;
  mountAmbientClock(root.querySelector(".vd-heading"), "dashboard");
  let model = JSON.parse(document.getElementById("vd-model").textContent);
  const area = document.getElementById("vd-area"),
    search = document.getElementById("vd-search");
  const board = document.getElementById("vd-board"),
    gallery = document.getElementById("vd-gallery"),
    map = document.getElementById("vd-map");
  const boardStatus = document.getElementById("vd-board-status");
  const propertySignals = document.getElementById("vd-property-signals");
  const cameraId = (name) => `camera-${encodeURIComponent(name)}`;
  const filter = document.getElementById("vd-filter");
  const dialog = document.getElementById("vd-detail");
  let detailCapture = null;
  let detailCameraNames = [];
  let replay = null,
    returnFocus = null,
    returnFocusName = "";
  let disposed = false,
    suspended = false;
  let boardLive = new Map();
  let boardKey = "";
  let boardRecords = [];
  let boardRotation = 0;
  let liveRotation = 0;
  let refreshCount = 0;
  const liveRetryUntil = new Map();
  const stopBoardLive = () => {
    boardLive.forEach((session) => session.dispose());
    boardLive.clear();
  };
  const needsAttention = (camera) =>
    Boolean(camera.issue || sourceNeedsAttention(camera.freshness));
  const closeDetails = () => {
    detailCapture?.dispose();
    replay?.dispose();
    replay = null;
    if (typeof dialog.close === "function") dialog.close();
    else dialog.removeAttribute("open");
    const target = returnFocus?.isConnected
      ? returnFocus
      : [...root.querySelectorAll("[data-vd-camera-name]")].find(
          (node) =>
            node.dataset.vdCameraName === returnFocusName &&
            node.tagName === returnFocus?.tagName,
        );
    (target || search).focus({ preventScroll: true });
  };
  document
    .getElementById("vd-detail-close")
    .addEventListener("click", closeDetails);
  dialog.addEventListener("close", () => {
    detailCapture?.dispose();
    replay?.dispose();
    replay = null;
  });
  dialog.addEventListener("cancel", (event) => {
    event.preventDefault();
    closeDetails();
  });
  const openDetails = (camera, trigger, browsing = false) => {
    if (!browsing) {
      detailCameraNames = [...gallery.querySelectorAll(".vd-card")]
        .map(
          (item) =>
            item.querySelector("[data-vd-camera-name]")?.dataset.vdCameraName,
        )
        .filter(Boolean);
      if (!detailCameraNames.includes(camera.name))
        detailCameraNames = model.cameras
          .filter((item) => item.group === camera.group)
          .map((item) => item.name);
    }
    // Keep the user's browsing order, but skip feeds removed by a refresh.
    const available = new Map(model.cameras.map((item) => [item.name, item]));
    detailCameraNames = detailCameraNames.filter((name) => available.has(name));
    detailCapture?.dispose();
    replay?.dispose();
    replay = null;
    returnFocus = trigger;
    returnFocusName = camera.name;
    document.getElementById("vd-detail-title").textContent = camera.name;
    const content = document.getElementById("vd-detail-content");
    detailCapture = createDetailCapture(camera);
    const captured = el(
      "p",
      "vd-detail-time",
      `Captured ${captureAge(camera.captured)}`,
    );
    captured.dataset.vdCaptured = camera.captured;
    const source = el("p", "vd-source", sourceAge(camera.freshness));
    source.dataset.vdFreshness = JSON.stringify(camera.freshness || {});
    source.classList.toggle(
      "is-source-older",
      sourceNeedsAttention(camera.freshness),
    );
    const replayHost = el("div", "vd-detail-replay");
    const actions = el("div", "vd-actions");
    const live = el(
      "a",
      "vd-action",
      ["rtsp", "hls", "mjpeg"].includes(camera.media_kind)
        ? "Open live video ↗"
        : "Open camera player ↗",
    );
    live.href = safeMediaUrl(camera.live);
    actions.append(live);
    if (camera.buffer_enabled) {
      const button = el("button", "vd-action", "Play recent replay");
      button.type = "button";
      button.addEventListener("click", () => {
        replay?.dispose();
        replay = mountMotionPreview(camera.name, replayHost);
        // Put feedback before long captions and keep it clear of the sticky
        // header. Avoid animated scrolling on an ambient/night display.
        replay.panel.scrollIntoView?.({ block: "start", behavior: "auto" });
      });
      actions.append(button);
    }
    const position = detailCameraNames.indexOf(camera.name);
    if (position >= 0 && detailCameraNames.length > 1) {
      for (const [direction, offset, label] of [
        ["previous", -1, "Previous camera"],
        ["next", 1, "Next camera"],
      ]) {
        const button = el("button", "vd-action", label);
        button.type = "button";
        button.dataset.vdBrowse = direction;
        button.disabled = !detailCameraNames[position + offset];
        button.addEventListener("click", () => {
          // Resolve against current metadata when clicked, not the opening snapshot.
          const candidates = detailCameraNames.slice();
          const nextName =
            offset > 0
              ? candidates
                  .slice(position + 1)
                  .find((name) =>
                    model.cameras.some((item) => item.name === name),
                  )
              : candidates
                  .slice(0, position)
                  .reverse()
                  .find((name) =>
                    model.cameras.some((item) => item.name === name),
                  );
          const next = model.cameras.find((item) => item.name === nextName);
          if (!next) return;
          const nextTrigger =
            document
              .getElementById(cameraId(next.name))
              ?.querySelector(".vd-action") || trigger;
          openDetails(next, nextTrigger, true);
          const preferred = content.querySelector(
            `[data-vd-browse="${direction}"]:not(:disabled)`,
          );
          (
            preferred ||
            content.querySelector("[data-vd-browse]:not(:disabled)") ||
            document.getElementById("vd-detail-close")
          ).focus({ preventScroll: true });
        });
        actions.append(button);
      }
      const positionLabel = el(
        "span",
        "vd-note",
        `${position + 1} of ${detailCameraNames.length} views`,
      );
      positionLabel.setAttribute("role", "status");
      actions.append(positionLabel);
    }
    const note = el(
      "p",
      "vd-note",
      "Capture time is when Glimpser saved this view. Source time refers to the original image when the publisher supplies it. Unchanged does not necessarily mean broken.",
    );
    const metadata = el("div", "vd-detail-metadata");
    metadata.append(captured, source);
    const help = el("details", "vd-detail-help");
    help.append(el("summary", "", "About timestamps and replays"), note);
    content.replaceChildren(
      detailCapture.node,
      actions,
      replayHost,
      metadata,
      el(
        "p",
        "vd-detail-caption",
        camera.caption || "No scene description yet.",
      ),
      descriptionTime(camera),
    );
    if (camera.issue)
      metadata.append(
        el("p", "vd-detail-issue", camera.issue.replaceAll("_", " ")),
      );
    if (camera.motion_at)
      metadata.append(
        el(
          "p",
          "vd-note",
          `Last detected motion: ${captureAge(camera.motion_at)}`,
        ),
      );
    if (camera.buffer_enabled)
      help.append(
        el(
          "p",
          "vd-note",
          "Replays use recent buffered frames at their recorded pace. Open live video for smoother motion when supported.",
        ),
      );
    content.append(help);
    if (!dialog.open) {
      if (typeof dialog.showModal === "function") dialog.showModal();
      else dialog.setAttribute("open", "");
    }
    dialog.scrollTop = 0;
  };

  const descriptionTime = (camera) => {
    const node = el("p", "vd-caption-age", captionAge(camera.caption_at));
    node.dataset.captionAge = camera.caption_at || "";
    return node;
  };
  const card = (camera, combined = false) => {
    const item = el("article", "vd-card");
    if (!combined) item.id = cameraId(camera.name);
    const link = el("a");
    link.href = safeMediaUrl(camera.live);
    link.dataset.vdCameraName = camera.name;
    link.setAttribute("aria-label", `Inspect ${camera.name}`);
    link.addEventListener("click", (event) => {
      event.preventDefault();
      openDetails(camera, link);
    });
    const image = el("img");
    if (root.dataset.visualDashboard !== "health")
      image.src = captureImageUrl(camera.image, camera.captured);
    image.alt = `${camera.name} latest capture`;
    image.loading = combined ? "eager" : "lazy";
    image.decoding = "async";
    let triedSavedFrame = false;
    image.addEventListener("error", async () => {
      // Capture metadata can differ by a few seconds from the saved filename.
      // Ask the image route for its actual canonical capture time before
      // treating a camera as unavailable.
      if (!triedSavedFrame && image.src.includes("capture=")) {
        triedSavedFrame = true;
        try {
          const response = await fetch(camera.image, {
            method: "HEAD",
            credentials: "same-origin",
          });
          const savedAt = response.headers.get("X-Capture-Time");
          if (response.ok && savedAt) {
            camera.captured = savedAt;
            age.textContent = `Captured ${captureAge(savedAt)}`;
            age.dataset.vdCaptured = savedAt;
            age.title = `${savedAt} UTC`;
            image.src = captureImageUrl(camera.image, savedAt);
            return;
          }
        } catch {
          // Keep the explicit unavailable state below when the retry fails.
        }
      }
      image.classList.add("vd-image-unavailable");
      image.alt = `${camera.name}: saved image unavailable`;
    });
    if (root.dataset.visualDashboard !== "health") {
      if (combined) {
        const media = el("div", "landing-hero-media");
        media.append(image);
        link.append(media);
        item.dataset.heroName = camera.name;
        item.dataset.heroMediaKind = camera.media_kind || "";
      } else link.append(image);
      item.append(link);
    } else {
      image.removeAttribute("src");
    }
    const heading = el("header");
    heading.append(el("h3", "", camera.name));
    const age = el("span", "vd-age", `Captured ${captureAge(camera.captured)}`);
    age.dataset.vdCaptured = camera.captured;
    age.title = camera.captured ? `${camera.captured} UTC` : "Awaiting capture";
    heading.append(age);
    item.append(heading);
    const source = el("p", "vd-source", sourceAge(camera.freshness));
    source.dataset.vdFreshness = JSON.stringify(camera.freshness || {});
    if (combined)
      source.dataset.sourceFreshness = JSON.stringify(camera.freshness || {});
    source.classList.toggle(
      "is-source-older",
      sourceNeedsAttention(camera.freshness),
    );
    item.append(source);
    item.classList.toggle("vd-needs-attention", needsAttention(camera));

    if (camera.issue)
      item.append(el("p", "vd-issue", camera.issue.replaceAll("_", " ")));
    else if (!combined && camera.caption)
      item.append(el("p", "vd-card-caption", camera.caption));
    if (!combined && camera.caption) item.append(descriptionTime(camera));
    if (!combined) {
      const actions = el("div", "vd-card-actions");
      const inspect = el("button", "vd-action", "Details");
      inspect.type = "button";
      inspect.dataset.vdCameraName = camera.name;
      inspect.addEventListener("click", () => openDetails(camera, inspect));
      actions.append(inspect);
      if (camera.buffer_enabled)
        actions.append(el("span", "vd-media-tag", "Replay buffer"));
      else if (["rtsp", "hls", "mjpeg"].includes(camera.media_kind))
        actions.append(el("span", "vd-media-tag", "Video source"));
      item.append(actions);
    }
    return item;
  };
  const startBoardLive = (records, key) => {
    if (
      disposed ||
      suspended ||
      document.hidden ||
      root.dataset.visualDashboard === "health"
    )
      return;
    const eligible = records
      .filter((record) => !needsAttention(record.camera))
      .filter(
        (record) =>
          Number(liveRetryUntil.get(record.camera.name)) <= Date.now() ||
          !liveRetryUntil.has(record.camera.name),
      )
      .filter((record) => livePilotEligible(record.card, "living"));
    const desired = selectBoardLive(eligible, area.value, liveRotation);
    const names = new Set(desired.map((record) => record.camera.name));
    boardLive.forEach((session, name) => {
      if (!names.has(name)) {
        session.dispose();
        boardLive.delete(name);
      }
    });
    for (const record of desired) {
      const name = record.camera.name;
      if (boardLive.has(name)) continue;
      const session = mountKioskLive(record.card, {
        onUnavailable: () => {
          liveRetryUntil.set(name, Date.now() + 300000);
          window.setTimeout(() => {
            if (boardKey !== key) return;
            boardLive.get(name)?.dispose();
            boardLive.delete(name);
            startBoardLive(records, key);
          }, 0);
        },
      });
      boardLive.set(name, session);
    }
  };
  const syncBoardRecord = (record, fresh) => {
    const shownAt = record.age.dataset.vdCaptured || record.displayedCapture;
    record.displayedCapture = shownAt;
    const shownFreshness = record.camera.freshness;
    Object.assign(record.camera, fresh, {
      captured: shownAt,
      freshness: shownFreshness,
    });
    record.card.dataset.heroMediaKind = fresh.media_kind || "";
    record.card.classList.toggle("vd-needs-attention", needsAttention(fresh));
    const showSource = () => {
      record.camera.freshness = fresh.freshness;
      record.source.textContent = sourceAge(fresh.freshness);
      record.source.dataset.vdFreshness = JSON.stringify(fresh.freshness || {});
      record.source.dataset.sourceFreshness = record.source.dataset.vdFreshness;
      record.source.classList.toggle(
        "is-source-older",
        sourceNeedsAttention(fresh.freshness),
      );
    };
    if (!fresh.captured || fresh.captured === shownAt) {
      showSource();
      return;
    }
    const serial = ++record.serial;
    const loadCapture = (captured, retried = false) => {
      const next = new Image();
      next.onload = () => {
        if (!record.active || serial !== record.serial) return;
        record.image.src = next.src;
        record.displayedCapture = captured;
        record.camera.captured = captured;
        record.age.dataset.vdCaptured = captured;
        record.age.textContent = `Captured ${captureAge(captured)}`;
        record.age.title = `${captured} UTC`;
        showSource();
      };
      next.onerror = async () => {
        if (!record.active || serial !== record.serial || retried) return;
        try {
          const response = await fetch(fresh.image, {
            method: "HEAD",
            credentials: "same-origin",
          });
          const savedAt = response.headers.get("X-Capture-Time");
          if (
            response.ok &&
            savedAt &&
            savedAt !== captured &&
            record.active &&
            serial === record.serial
          )
            loadCapture(savedAt, true);
        } catch {
          // The displayed capture and its age remain unchanged.
        }
      };
      next.src = captureImageUrl(fresh.image, captured);
    };
    loadCapture(fresh.captured);
  };
  const renderBoardStatus = (members) => {
    const alerts = members.filter(needsAttention);
    boardStatus.hidden = !alerts.length;
    if (!alerts.length) {
      boardStatus.replaceChildren();
      return;
    }
    const button = el(
      "button",
      "vd-board-alert",
      `${alerts.length} feed${alerts.length === 1 ? "" : "s"} to review · ${alerts
        .slice(0, 3)
        .map((camera) => camera.name)
        .join(", ")}${alerts.length > 3 ? "…" : ""}`,
    );
    button.type = "button";
    button.addEventListener("click", () => {
      filter.value = "attention";
      search.value = area.value;
      renderGallery();
      gallery
        .closest(".vd-gallery-section")
        ?.scrollIntoView({ block: "start" });
    });
    boardStatus.replaceChildren(button);
  };
  const renderPropertySignals = () => {
    if (!propertySignals) return;
    const beach = area.value === "Beach property health";
    document.getElementById("vd-property-title").textContent = beach
      ? "Beach house status"
      : "Water, power & climate";
    const entries = selectPropertySignals(model.cameras, area.value);
    propertySignals.replaceChildren(
      ...entries.map(({ camera, label }) => {
        const button = el("button", "vd-signal");
        button.type = "button";
        if (!camera) {
          button.disabled = true;
          const copy = el("span", "vd-signal-copy");
          copy.append(el("strong", "", label), el("span", "", "Awaiting feed"));
          button.append(el("span", "vd-signal-placeholder", "—"), copy);
          return button;
        }
        const image = el("img");
        button.dataset.vdCameraName = camera.name;
        image.src = captureImageUrl(camera.image, camera.captured);
        image.alt = "";
        image.loading = "lazy";
        const copy = el("span", "vd-signal-copy");
        copy.append(
          el("strong", "", label),
          el("span", "", `Captured ${captureAge(camera.captured)}`),
          el(
            "small",
            "",
            camera.issue
              ? camera.issue.replaceAll("_", " ")
              : sourceNeedsAttention(camera.freshness)
                ? "Review source age"
                : "Open status page",
          ),
        );
        button.classList.toggle("vd-needs-attention", needsAttention(camera));
        button.append(image, copy);
        button.addEventListener("click", () => openDetails(camera, button));
        return button;
      }),
    );
  };
  const renderBoard = () => {
    const members = model.cameras.filter((c) => c.group === area.value);
    const selected = selectBoardCameras(
      selectBoardCandidates(members, area.value),
      area.value,
      boardRotation,
      Date.now(),
    );
    const key = `${area.value}:${selected
      .map(
        (camera) =>
          `${camera.name}/${camera.media_kind}/${needsAttention(camera)}`,
      )
      .join("|")}`;
    renderBoardStatus(members);
    if (key === boardKey && boardRecords.length === selected.length) {
      boardRecords.forEach((record, index) =>
        syncBoardRecord(record, selected[index]),
      );
      startBoardLive(boardRecords, key);
      return;
    }
    stopBoardLive();
    boardRecords.forEach((record) => {
      record.active = false;
    });
    boardKey = key;
    boardRecords = selected.map((camera) => {
      const item = card(camera, true);
      return {
        active: true,
        age: item.querySelector(".vd-age"),
        camera,
        card: item,
        displayedCapture: camera.captured,
        image: item.querySelector("img"),
        serial: 0,
        source: item.querySelector(".vd-source"),
      };
    });
    board.replaceChildren(...boardRecords.map((record) => record.card));
    if (!members.length)
      board.append(el("p", "vd-note", "No cameras in this area yet."));
    startBoardLive(boardRecords, key);
  };
  const renderGallery = () => {
    // Refresh metadata without moving keyboard users back to the page body.
    const focused = document.activeElement;
    const focusedCard = gallery.contains(focused)
      ? focused.closest(".vd-card")
      : null;
    const focusedId = focusedCard?.id;
    const focusedTag = focused?.tagName;
    const term = search.value.trim().toLowerCase();
    gallery.replaceChildren(
      ...model.cameras
        .filter((c) => `${c.name} ${c.group}`.toLowerCase().includes(term))
        .filter((c) =>
          filter.value === "attention"
            ? needsAttention(c)
            : filter.value === "motion"
              ? c.buffer_enabled
              : true,
        )
        .map((c) => card(c)),
    );
    document.getElementById("vd-results").textContent =
      `${gallery.childElementCount} views shown`;
    if (!gallery.childElementCount) {
      const empty = el("div", "vd-empty");
      empty.append(el("p", "", "No cameras match these filters."));
      if (term || filter.value !== "all") {
        const reset = el("button", "vd-action", "Show all cameras");
        reset.type = "button";
        reset.addEventListener("click", () => {
          search.value = "";
          filter.value = "all";
          renderGallery();
          search.focus({ preventScroll: true });
        });
        empty.append(reset);
      }
      gallery.append(empty);
    }
    if (focusedId) {
      const replacement = document.getElementById(focusedId);
      const target =
        focused === focusedCard
          ? replacement
          : replacement?.querySelector(
              focusedTag === "BUTTON" ? ".vd-action" : "a",
            );
      if (target === replacement && target) target.tabIndex = -1;
      (target || search).focus({ preventScroll: true });
    }
  };
  const selectCamera = (event, name) => {
    event.preventDefault();
    search.value = "";
    filter.value = "all";
    renderGallery();
    const target = document.getElementById(cameraId(name));
    if (target) {
      target.classList.add("is-selected");
      target.scrollIntoView?.({ block: "center" });
      target.tabIndex = -1;
      target.focus({ preventScroll: true });
    }
  };
  const renderMap = () => {
    const focused = map.contains(document.activeElement)
      ? document.activeElement
      : null;
    const focusedHref = focused?.getAttribute("href");
    const restoreMapFocus = () => {
      if (!focused) return;
      const target =
        focused.tagName === "SELECT"
          ? map.querySelector("select")
          : [...map.querySelectorAll("a")].find(
              (node) => node.getAttribute("href") === focusedHref,
            );
      (target || map.querySelector("select, a") || search).focus({
        preventScroll: true,
      });
    };
    map.replaceChildren();
    const groups = [
      ...new Set(model.cameras.filter((c) => c.location).map((c) => c.group)),
    ];
    const scope = groups.includes(root.dataset.mapScope)
      ? root.dataset.mapScope
      : "";
    root.dataset.mapScope = scope;
    if (groups.length) {
      const label = el("label", "vd-map-filter", "Map area ");
      const select = el("select");
      select.setAttribute("aria-label", "Map area");
      ["", ...groups].forEach((group) => {
        const option = el("option", "", group || "All mapped cameras");
        option.value = group;
        select.append(option);
      });
      select.value = scope;
      select.addEventListener("change", () => {
        root.dataset.mapScope = select.value;
        renderMap();
      });
      label.append(select);
      map.append(label);
    }
    const points = projectLocations(
      model.cameras.filter((c) => !scope || c.group === scope),
    );
    document.getElementById("vd-map-title").textContent = points.length
      ? "Camera minimap"
      : "Camera overview";
    document.getElementById("vd-map-note").textContent = points.length
      ? `${points.length} recorded locations • north is up • geographic plot • close markers separated with guide lines`
      : "Locations are not mapped. This is a camera index, not a floor plan.";
    if (!points.length) {
      const list = el("div", "vd-map-list");
      model.cameras.slice(0, 16).forEach((c) => {
        const a = el("a", "", c.name);
        a.href = `#${cameraId(c.name)}`;
        a.addEventListener("click", (e) => selectCamera(e, c.name));
        list.append(a);
      });
      map.append(list);
      restoreMapFocus();
      return;
    }
    const svg = svgEl("svg", {
      viewBox: "0 0 500 280",
      role: "group",
      "aria-label": "Camera location minimap",
    });
    for (let x = 50; x < 500; x += 50)
      svg.append(
        svgEl("line", { x1: x, x2: x, y1: 20, y2: 260, class: "vd-map-grid" }),
      );
    for (let y = 40; y < 280; y += 40)
      svg.append(
        svgEl("line", { x1: 20, x2: 480, y1: y, y2: y, class: "vd-map-grid" }),
      );
    const north = svgEl("text", { x: 18, y: 18 });
    north.textContent = "N ↑";
    svg.append(north);
    const labels = [];
    const markers = [];
    points.forEach((point) => {
      const p = { ...point };
      for (
        let attempt = 0;
        attempt < 100 &&
        markers.some((m) => Math.hypot(m.x - p.x, m.y - p.y) < 18);
        attempt++
      ) {
        const angle = attempt * 2.39996;
        const radius = 12 + Math.sqrt(attempt) * 7;
        p.x = Math.max(18, Math.min(482, point.x + Math.cos(angle) * radius));
        p.y = Math.max(26, Math.min(260, point.y + Math.sin(angle) * radius));
      }
      markers.push(p);
      if (p.x !== point.x || p.y !== point.y) {
        svg.append(
          svgEl("line", {
            x1: point.x,
            y1: point.y,
            x2: p.x,
            y2: p.y,
            class: "vd-map-leader",
          }),
        );
      }
      const a = svgEl("a", {
        href: `#${cameraId(p.camera.name)}`,
        "aria-label": p.camera.name,
        tabindex: 0,
      });
      const title = svgEl("title", {});
      title.textContent = `${p.camera.name} · ${p.camera.location.label} · ${p.camera.location.accuracy}`;
      a.append(
        title,
        svgEl("circle", {
          cx: p.x,
          cy: p.y,
          r: 7,
          class: p.camera.issue ? "vd-map-held" : "",
        }),
      );
      const labelX = Math.min(p.x + 10, 370);
      if (
        !labels.some(
          (l) => Math.abs(l.x - labelX) < 125 && Math.abs(l.y - p.y) < 17,
        )
      ) {
        labels.push({ x: labelX, y: p.y });
        const label = svgEl("text", { x: labelX, y: p.y - 9 });
        label.textContent = p.camera.name.slice(0, 18);
        a.append(label);
      }
      a.addEventListener("click", (e) => selectCamera(e, p.camera.name));
      svg.append(a);
    });
    map.append(svg);
    restoreMapFocus();
  };
  const render = () => {
    const preferred = {
      arrivals: presentationValue("Home arrivals"),
      property: presentationValue("Home property health"),
      "beach-conditions": "Nearby lake conditions",
    };
    const selected = area.value || preferred[model.dashboard] || "";
    area.replaceChildren(
      ...[...new Set(model.cameras.map((c) => c.group))].map((group) => {
        const option = el("option", "", group);
        option.value = group;
        return option;
      }),
    );
    if ([...area.options].some((o) => o.value === selected))
      area.value = selected;
    document.getElementById("vd-total").textContent = model.cameras.length;
    document.getElementById("vd-healthy").textContent = model.healthy;
    document.getElementById("vd-attention").textContent =
      model.attention ?? model.cameras.filter(needsAttention).length;
    document.getElementById("vd-mapped").textContent =
      root.dataset.visualDashboard === "property"
        ? (model.live_capable ??
          model.cameras.filter((camera) =>
            ["rtsp", "hls", "mjpeg"].includes(camera.media_kind),
          ).length)
        : model.mapped;
    const health = document.getElementById("vd-health-counts");
    if (health && model.health_summary) {
      const h = model.health_summary;
      health.textContent = `${h.total} active feeds · ${h.failed} capture failures · ${h.overdue} overdue / awaiting · ${h.source} source-age alerts · ${h.blocked} blocked pages`;
    }
    if (root.dataset.visualDashboard !== "health") {
      renderBoard();
      if (map) renderMap();
      renderPropertySignals();
    }
    renderGallery();
  };
  area.addEventListener("change", () => {
    renderBoard();
    renderPropertySignals();
  });
  const handleVisibility = () => {
    if (disposed || suspended) return;
    if (document.hidden) {
      cancelRefresh();
      stopBoardLive();
    } else {
      if (root.dataset.visualDashboard !== "health") renderBoard();
      refresh();
    }
  };
  document.addEventListener("visibilitychange", handleVisibility);
  search.addEventListener("input", renderGallery);
  filter.addEventListener("change", renderGallery);
  render();
  const updateAges = () => {
    root.querySelectorAll("[data-vd-captured]").forEach((n) => {
      n.textContent = `Captured ${captureAge(n.dataset.vdCaptured)}`;
    });
    root.querySelectorAll("[data-caption-age]").forEach((n) => {
      n.textContent = captionAge(n.dataset.captionAge);
    });
    root.querySelectorAll("[data-vd-freshness]").forEach((n) => {
      n.textContent = sourceAge(JSON.parse(n.dataset.vdFreshness || "{}"));
    });
  };
  let ageTimer = window.setInterval(updateAges, 10000);
  let activeRefresh = null;
  const cancelRefresh = () => {
    const pending = activeRefresh;
    // Release synchronously so a visibility/online/pageshow event can replace
    // the request even before its rejected promise has finished unwinding.
    activeRefresh = null;
    pending?.cancel();
  };
  const refresh = async () => {
    if (disposed || suspended || document.hidden || activeRefresh) return;
    const request = {};
    activeRefresh = request;
    const controller =
      typeof AbortController === "function" ? new AbortController() : null;
    // Abort is advisory; the deadline also releases the refresh lock when
    // transport or body decoding does not respond to cancellation.
    let timeout;
    const deadline = new Promise((_, reject) => {
      request.cancel = () => {
        controller?.abort();
        reject(new Error("Refresh interrupted"));
      };
      timeout = window.setTimeout(request.cancel, 8000);
    });
    try {
      const next = await Promise.race([
        (async () => {
          const response = await fetch(
            `/dashboard/${encodeURIComponent(root.dataset.visualDashboard)}/data`,
            { cache: "no-store", signal: controller?.signal },
          );
          if (!response.ok) throw new Error("Refresh unavailable");
          return response.json();
        })(),
        deadline,
      ]);
      if (disposed || suspended || document.hidden || activeRefresh !== request)
        return;
      if (
        !Array.isArray(next?.cameras) ||
        next.cameras.some(
          (camera) =>
            !camera || typeof camera.name !== "string" || !camera.name.trim(),
        )
      )
        throw new Error("Invalid camera metadata");
      model = next;
      refreshCount += 1;
      liveRotation += 1;
      if (refreshCount % 2 === 0) boardRotation += 1;
      render();
      document.getElementById("vd-refresh-status").textContent =
        "Capture metadata refreshed just now.";
    } catch {
      if (disposed || suspended || document.hidden || activeRefresh !== request)
        return;
      document.getElementById("vd-refresh-status").textContent =
        "Refresh delayed; showing the last received captures.";
    } finally {
      window.clearTimeout(timeout);
      if (activeRefresh === request) activeRefresh = null;
    }
  };
  let refreshTimer = window.setInterval(refresh, 60000);
  const handlePageShow = (event) => {
    if (!event.persisted || disposed || !suspended) return;
    suspended = false;
    updateAges();
    handleVisibility();
    ageTimer = window.setInterval(updateAges, 10000);
    refreshTimer = window.setInterval(refresh, 60000);
  };
  const handlePageHide = (event) => {
    suspended = true;
    disposed = !event.persisted;
    cancelRefresh();
    closeDetails();
    stopBoardLive();
    window.clearInterval(ageTimer);
    window.clearInterval(refreshTimer);
    if (disposed) {
      document.removeEventListener("visibilitychange", handleVisibility);
      window.removeEventListener("pageshow", handlePageShow);
      window.removeEventListener("pagehide", handlePageHide);
      window.removeEventListener("offline", cancelRefresh);
      window.removeEventListener("online", refresh);
    }
  };
  window.addEventListener("pageshow", handlePageShow);
  window.addEventListener("pagehide", handlePageHide);
  window.addEventListener("offline", cancelRefresh);
  window.addEventListener("online", refresh);
}
initVisualDashboard();
