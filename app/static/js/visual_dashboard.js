import { mountAmbientClock } from "./ambient_clock.js";
import {
  captionAge,
  safeMediaUrl,
  captureImageUrl,
  captureAge,
  sourceAge,
  sourceNeedsAttention,
} from "./capture_age.js";
import { mountMotionPreview } from "./motion_preview.js";

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
  const cameraId = (name) => `camera-${encodeURIComponent(name)}`;
  const filter = document.getElementById("vd-filter");
  const dialog = document.getElementById("vd-detail");
  let replay = null,
    returnFocus = null;
  const needsAttention = (camera) =>
    Boolean(camera.issue || sourceNeedsAttention(camera.freshness));
  const closeDetails = () => {
    replay?.dispose();
    replay = null;
    if (typeof dialog.close === "function") dialog.close();
    else dialog.removeAttribute("open");
    returnFocus?.focus();
  };
  document
    .getElementById("vd-detail-close")
    .addEventListener("click", closeDetails);
  dialog.addEventListener("close", () => {
    replay?.dispose();
    replay = null;
  });
  dialog.addEventListener("cancel", () => {
    replay?.dispose();
    replay = null;
  });
  const openDetails = (camera, trigger) => {
    replay?.dispose();
    replay = null;
    returnFocus = trigger;
    document.getElementById("vd-detail-title").textContent = camera.name;
    const content = document.getElementById("vd-detail-content");
    const image = el("img", "vd-detail-image");
    image.src = captureImageUrl(camera.image, camera.captured);
    image.alt = `${camera.name} saved capture`;
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
        replay = mountMotionPreview(camera.name, content);
      });
      actions.append(button);
    }
    const note = el(
      "p",
      "vd-note",
      "Capture time is when Glimpser saved this view. Source time refers to the original image when the publisher supplies it. Unchanged does not necessarily mean broken.",
    );
    content.replaceChildren(
      image,
      captured,
      source,
      el(
        "p",
        "vd-detail-caption",
        camera.caption || "No scene description yet.",
      ),
      descriptionTime(camera),
      actions,
      note,
    );
    if (camera.motion_at)
      content.append(
        el(
          "p",
          "vd-note",
          `Last detected motion: ${captureAge(camera.motion_at)}`,
        ),
      );
    if (camera.buffer_enabled)
      content.append(
        el(
          "p",
          "vd-note",
          "Replays use recent buffered frames at their recorded pace. Open live video for smoother motion when supported.",
        ),
      );
    if (typeof dialog.showModal === "function") dialog.showModal();
    else dialog.setAttribute("open", "");
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
      link.append(image);
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
    source.classList.toggle(
      "is-source-older",
      sourceNeedsAttention(camera.freshness),
    );
    item.append(source);
    item.classList.toggle("vd-needs-attention", needsAttention(camera));

    if (camera.issue)
      item.append(el("p", "vd-issue", camera.issue.replaceAll("_", " ")));
    else if (!combined) item.append(el("p", "", camera.caption));
    if (!combined && camera.caption) item.append(descriptionTime(camera));
    if (!combined) {
      const actions = el("div", "vd-card-actions");
      const inspect = el("button", "vd-action", "Details");
      inspect.type = "button";
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
  const renderBoard = () => {
    const members = model.cameras.filter((c) => c.group === area.value);
    const healthy = members.filter((c) => !needsAttention(c));
    board.replaceChildren(
      ...(healthy.length ? healthy : members)
        .slice(0, 6)
        .map((c) => card(c, true)),
    );
    if (!members.length)
      board.append(el("p", "vd-note", "No cameras in this area yet."));
  };
  const renderGallery = () => {
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
    if (!gallery.childElementCount)
      gallery.append(el("p", "vd-empty", "No cameras match these filters."));
  };
  const selectCamera = (event, name) => {
    event.preventDefault();
    search.value = "";
    renderGallery();
    const target = document.getElementById(cameraId(name));
    if (target) {
      target.classList.add("is-selected");
      target.scrollIntoView({ block: "center" });
      target.tabIndex = -1;
      target.focus({ preventScroll: true });
    }
  };
  const renderMap = () => {
    map.replaceChildren();
    const groups = [
      ...new Set(model.cameras.filter((c) => c.location).map((c) => c.group)),
    ];
    const scope = root.dataset.mapScope || "";
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
  };
  const render = () => {
    const selected = area.value || model.preferred_area || "";
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
    document.getElementById("vd-mapped").textContent = model.mapped;
    const health = document.getElementById("vd-health-counts");
    if (health && model.health_summary) {
      const h = model.health_summary;
      health.textContent = `${h.total} active feeds · ${h.failed} capture failures · ${h.overdue} overdue / awaiting · ${h.source} source-age alerts · ${h.blocked} blocked pages`;
    }
    if (root.dataset.visualDashboard !== "health") {
      renderBoard();
      renderMap();
    }
    renderGallery();
  };
  area.addEventListener("change", renderBoard);
  search.addEventListener("input", renderGallery);
  filter.addEventListener("change", renderGallery);
  render();
  const ageTimer = window.setInterval(() => {
    root.querySelectorAll("[data-vd-captured]").forEach((n) => {
      n.textContent = `Captured ${captureAge(n.dataset.vdCaptured)}`;
    });
    root.querySelectorAll("[data-caption-age]").forEach((n) => {
      n.textContent = captionAge(n.dataset.captionAge);
    });
    root.querySelectorAll("[data-vd-freshness]").forEach((n) => {
      n.textContent = sourceAge(JSON.parse(n.dataset.vdFreshness || "{}"));
    });
  }, 10000);
  let inFlight = false;
  const refreshTimer = window.setInterval(async () => {
    if (document.hidden || inFlight) return;
    inFlight = true;
    const controller =
      typeof AbortController === "function" ? new AbortController() : null;
    const timeout = window.setTimeout(() => controller?.abort(), 8000);
    try {
      const response = await fetch(
        `/dashboard/${encodeURIComponent(root.dataset.visualDashboard)}/data`,
        { cache: "no-store", signal: controller?.signal },
      );
      if (!response.ok) throw new Error("Refresh unavailable");
      model = await response.json();
      render();
      document.getElementById("vd-refresh-status").textContent =
        "Capture metadata refreshed just now.";
    } catch {
      document.getElementById("vd-refresh-status").textContent =
        "Refresh delayed; showing the last received captures.";
    } finally {
      window.clearTimeout(timeout);
      inFlight = false;
    }
  }, 60000);
  window.addEventListener(
    "pagehide",
    () => {
      replay?.dispose();
      window.clearInterval(ageTimer);
      window.clearInterval(refreshTimer);
    },
    { once: true },
  );
}
initVisualDashboard();
