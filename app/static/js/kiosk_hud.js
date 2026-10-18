import { mountAmbientClock } from "./ambient_clock.js?v=20260926-3";
import {
  captionAge,
  captureAge,
  sourceAge,
  sourceNeedsAttention,
} from "./capture_age.js";

// Independent startup keeps the prominent age readable even if rotation startup stalls.
export function updateKioskAges(root = document) {
  root.querySelectorAll("[data-capture-age]").forEach((node) => {
    node.textContent = captureAge(node.dataset.captureAge);
  });
  root.querySelectorAll("[data-caption-age]").forEach((node) => {
    node.textContent = captionAge(node.dataset.captionAge);
  });
  root.querySelectorAll("[data-source-freshness]").forEach((node) => {
    let freshness = {};
    try {
      freshness = JSON.parse(node.dataset.sourceFreshness || "{}");
    } catch {
      /* unknown metadata */
    }
    node.textContent = sourceAge(freshness);
    node.classList.toggle("is-source-older", sourceNeedsAttention(freshness));
  });
}
const svgNode = (tag, attrs) => {
  const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
  Object.entries(attrs).forEach(([key, value]) =>
    node.setAttribute(key, value),
  );
  return node;
};
export function drawKioskLocation(node, camera, cameras, nearby = []) {
  node.replaceChildren();
  const label = document.createElement("div");
  label.textContent =
    camera?.location?.label || node.dataset.areaLabel || "Camera view";
  node.append(label);
  if (!camera?.location) return;
  const { lat, lon } = camera.location;
  const svg = svgNode("svg", {
    viewBox: "0 0 240 105",
    role: "img",
    "aria-label": `Nearby camera locations; ${camera.name} highlighted. North is up.`,
  });
  svg.append(
    svgNode("rect", {
      x: 0,
      y: 0,
      width: 240,
      height: 105,
      rx: 8,
      fill: "#102337",
    }),
  );
  const nearbyCameras = cameras.filter(
    (c) =>
      c.location &&
      Math.abs(c.location.lat - lat) < 0.15 &&
      Math.abs(c.location.lon - lon) < 0.22,
  );
  nearbyCameras.forEach((c) =>
    svg.append(
      svgNode("circle", {
        cx:
          120 + (c.location.lon - lon) * 450 * Math.cos((lat * Math.PI) / 180),
        cy: 53 - (c.location.lat - lat) * 290,
        r: 3,
        fill: "#7697ac",
      }),
    ),
  );
  svg.append(
    svgNode("circle", {
      cx: 120,
      cy: 53,
      r: 8,
      fill: "#7affd4",
      stroke: "#fff",
      "stroke-width": 2,
    }),
  );
  const north = svgNode("text", {
    x: 10,
    y: 18,
    fill: "#fff",
    "font-size": 14,
  });
  north.textContent = "N ↑";
  svg.append(north);
  node.append(svg);
  const distances = nearby.flatMap((subject) =>
    subject.cameras
      .filter((c) => c.name === camera.name)
      .map((c) => ({ label: subject.label, distance: c.distance_m })),
  );
  if (distances.length) {
    distances.sort((a, b) => a.distance - b.distance);
    const closest = distances[0],
      note = document.createElement("small");
    note.textContent = `${closest.label} ≈ ${closest.distance < 1000 ? closest.distance + " m" : (closest.distance / 1000).toFixed(1) + " km"} away`;
    node.append(note);
  }
}
if (document.body.matches(".landing-profile-office, .landing-profile-living")) {
  mountAmbientClock(document.body);
}

if (document.querySelector(".kiosk-caption-strip")) {
  const stylesheet = document.createElement("link");
  stylesheet.rel = "stylesheet";
  stylesheet.href = "/static/css/kiosk_fullbleed.css?v=20260922-6";
  document.body.append(stylesheet);
  let nearby = [];
  let cameras = [],
    lastNode = null;
  const update = () => {
    updateKioskAges();
    const node = document.querySelector(
      ".landing-scene.is-visible [data-kiosk-location]",
    );
    if (node && node !== lastNode) {
      drawKioskLocation(
        node,
        cameras.find((c) => c.name === node.dataset.cameraName),
        cameras,
        nearby,
      );
      lastNode = node;
    }
  };
  update();
  const timer = window.setInterval(update, 1000);
  let inFlight = false,
    activeController = null;
  const refresh = async () => {
    if (inFlight || document.hidden) return;
    inFlight = true;
    activeController =
      typeof AbortController === "function" ? new AbortController() : null;
    const timeout = window.setTimeout(() => activeController?.abort(), 8000);
    try {
      const response = await fetch("/api/nearby-context", {
        cache: "no-store",
        signal: activeController?.signal,
      });
      if (!response.ok) throw new Error("Location context unavailable");
      const data = await response.json();
      cameras = data.cameras || [];
      nearby = data.nearby || [];
      lastNode = null;
      update();
    } catch {
      nearby = [];
      lastNode = null;
      update();
    } finally {
      window.clearTimeout(timeout);
      inFlight = false;
    }
  };
  refresh();
  const contextTimer = window.setInterval(refresh, 60000);
  window.addEventListener(
    "pagehide",
    () => {
      window.clearInterval(timer);
      window.clearInterval(contextTimer);
      activeController?.abort();
    },
    { once: true },
  );
}
