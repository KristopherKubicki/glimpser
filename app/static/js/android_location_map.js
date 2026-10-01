const freshnessModule = import("./map_freshness.js");
const presenceModule = import("./household_presence.js");
const dataNode = document.getElementById("location-data");
const mapNode = document.getElementById("location-map");
const tileLayer = document.getElementById("location-tile-layer");
const markerLayer = document.getElementById("location-marker-layer");
const listNode = document.getElementById("location-list");
const emptyNode = document.getElementById("location-empty-state");
const activeCountNode = document.getElementById("location-active-count");
const staleCountNode = document.getElementById("location-stale-count");
const providerCountNode = document.getElementById("location-provider-count");
const TILE_SIZE = 256;
const TILE_HOST = "https://tile.openstreetmap.org";
const FIT_PADDING_PX = 10;
let mapState = null;
let cameraPoints = [];
let catalogCameras = [];
let unmappedCameras = [];
let zoomDelta = 0;
let selectedNames = [];
let refreshing = false;
let lastLocations = [];
let householdCount = 0;
let lastHouseholdPayload = null;
let lastMapRefresh = null;
let mapOffline = false;
let tilesMissing = false;
const mapStatus = document.createElement("p");
mapStatus.className = "household-note";
mapStatus.setAttribute("role", "status");
mapNode.before(mapStatus);
const mapLegend = document.createElement("p");
mapLegend.className = "household-note";
mapLegend.textContent =
  "Numbered pins: camera views · Named pins: reported GPS · Faded pins: stale or offline. Camera capture time is not the source data time.";
mapNode.after(mapLegend);
async function updateMapStatus() {
  const { mapRefreshLabel } = await freshnessModule;
  mapStatus.textContent = mapRefreshLabel(
    lastMapRefresh,
    mapOffline,
    tilesMissing,
  );
}
const householdNode = document.createElement("section");
householdNode.className = "household-presence";
householdNode.setAttribute(
  "aria-label",
  "Household presence and nearby cameras",
);
listNode.before(householdNode);

async function renderHousehold(payload) {
  const { renderPresence } = await presenceModule;
  householdCount = (payload.subjects || []).length;
  renderPresence(householdNode, payload);
  lastHouseholdPayload = payload;
  const note = document.createElement("p");
  note.className = "household-note";
  note.textContent = `${payload.cameras.length} mapped views · nearby distances require fresh GPS.`;
  householdNode.append(note);
  for (const subject of payload.nearby || []) {
    const section = document.createElement("article");
    section.className = "household-person";
    const heading = document.createElement("strong");
    heading.textContent = `Near ${subject.label}`;
    section.append(heading);
    const accuracy = document.createElement("p");
    accuracy.textContent = `Approximate straight-line distances. GPS accuracy: ${subject.accuracy_m == null ? "unknown" : Math.round(subject.accuracy_m) + " m"}.`;
    section.append(accuracy);
    if (!subject.cameras.length) {
      const none = document.createElement("p");
      none.textContent = "No mapped cameras within 10 km.";
      section.append(none);
    }
    for (const camera of subject.cameras) {
      const link = document.createElement("a");
      link.href = camera.live;
      link.textContent = `${camera.name} · ${camera.distance_m < 1000 ? camera.distance_m + " m" : (camera.distance_m / 1000).toFixed(1) + " km"}`;
      section.append(link);
    }
    householdNode.append(section);
  }
}

function readInitialLocations() {
  if (!dataNode) {
    return [];
  }
  try {
    return JSON.parse(dataNode.textContent || "[]");
  } catch (_error) {
    return [];
  }
}

function formatAge(seconds) {
  if (seconds == null || !Number.isFinite(Number(seconds)))
    return "unknown age";
  const value = Number(seconds);
  if (value < 60) {
    return `${value}s`;
  }
  if (value < 3600) {
    return `${Math.round(value / 60)}m`;
  }
  if (value < 86400) {
    return `${Math.round(value / 3600)}h`;
  }
  return `${Math.round(value / 86400)}d`;
}

function formatNumber(value, digits = 1) {
  const number = Number(value);
  if (!Number.isFinite(number)) {
    return "n/a";
  }
  return number.toFixed(digits);
}

function sortedLocations(locations) {
  return [...locations].sort((left, right) => {
    if (Boolean(left.stale) !== Boolean(right.stale)) {
      return left.stale ? 1 : -1;
    }
    return String(left.label || "").localeCompare(String(right.label || ""));
  });
}

function locationBounds(locations) {
  const latitudes = locations.map((point) => Number(point.latitude));
  const longitudes = locations.map((point) => Number(point.longitude));
  let minLat = Math.min(...latitudes);
  let maxLat = Math.max(...latitudes);
  let minLon = Math.min(...longitudes);
  let maxLon = Math.max(...longitudes);

  if (minLat === maxLat) {
    minLat -= 0.01;
    maxLat += 0.01;
  }
  if (minLon === maxLon) {
    minLon -= 0.01;
    maxLon += 0.01;
  }

  const latPad = (maxLat - minLat) * 0.14;
  const lonPad = (maxLon - minLon) * 0.14;
  return {
    minLat: minLat - latPad,
    maxLat: maxLat + latPad,
    minLon: minLon - lonPad,
    maxLon: maxLon + lonPad,
  };
}

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function worldSize(zoom) {
  return TILE_SIZE * 2 ** zoom;
}

function projectLocation(point, zoom) {
  const latitude = clamp(Number(point.latitude), -85.05112878, 85.05112878);
  const longitude = Number(point.longitude);
  const sinLat = Math.sin((latitude * Math.PI) / 180);
  const scale = worldSize(zoom);
  return {
    x: ((longitude + 180) / 360) * scale,
    y: (0.5 - Math.log((1 + sinLat) / (1 - sinLat)) / (4 * Math.PI)) * scale,
  };
}

function chooseZoom(locations, width, height) {
  if (locations.length <= 1) {
    return 14;
  }
  for (let zoom = 18; zoom >= 3; zoom -= 1) {
    const projected = locations.map((point) => projectLocation(point, zoom));
    const xs = projected.map((point) => point.x);
    const ys = projected.map((point) => point.y);
    const spanX = Math.max(...xs) - Math.min(...xs);
    const spanY = Math.max(...ys) - Math.min(...ys);
    if (
      spanX <= width - FIT_PADDING_PX * 2 &&
      spanY <= height - FIT_PADDING_PX * 2
    ) {
      return zoom;
    }
  }
  return 3;
}

function renderTiles(locations) {
  tileLayer.replaceChildren();
  if (!locations.length || !mapNode) {
    mapState = null;
    return;
  }
  const rect = mapNode.getBoundingClientRect();
  const width = Math.max(320, rect.width);
  const height = Math.max(320, rect.height);
  const zoom = clamp(chooseZoom(locations, width, height) + zoomDelta, 3, 18);
  const projected = locations.map((point) => projectLocation(point, zoom));
  const xs = projected.map((point) => point.x);
  const ys = projected.map((point) => point.y);
  const centerX = (Math.min(...xs) + Math.max(...xs)) / 2;
  const centerY = (Math.min(...ys) + Math.max(...ys)) / 2;
  const topLeft = {
    x: centerX - width / 2,
    y: centerY - height / 2,
  };
  const startTileX = Math.floor(topLeft.x / TILE_SIZE);
  const endTileX = Math.floor((topLeft.x + width) / TILE_SIZE);
  const startTileY = Math.floor(topLeft.y / TILE_SIZE);
  const endTileY = Math.floor((topLeft.y + height) / TILE_SIZE);
  const maxTile = 2 ** zoom;

  for (let tileX = startTileX; tileX <= endTileX; tileX += 1) {
    for (let tileY = startTileY; tileY <= endTileY; tileY += 1) {
      if (tileY < 0 || tileY >= maxTile) {
        continue;
      }
      const wrappedX = ((tileX % maxTile) + maxTile) % maxTile;
      const image = document.createElement("img");
      image.className = "location-map-tile";
      image.alt = "";
      image.decoding = "async";
      image.referrerPolicy = "no-referrer";
      image.addEventListener("error", () => {
        if (!image.isConnected) return;
        image.style.visibility = "hidden";
        tilesMissing = true;
        updateMapStatus();
      });
      image.src = `${TILE_HOST}/${zoom}/${wrappedX}/${tileY}.png`;
      image.style.left = `${Math.round(tileX * TILE_SIZE - topLeft.x)}px`;
      image.style.top = `${Math.round(tileY * TILE_SIZE - topLeft.y)}px`;
      tileLayer.appendChild(image);
    }
  }

  mapState = { height, topLeft, width, zoom };
}

function markerPosition(point) {
  if (!mapState) {
    const bounds = locationBounds([point]);
    return {
      x:
        ((Number(point.longitude) - bounds.minLon) /
          (bounds.maxLon - bounds.minLon)) *
        100,
      y:
        ((bounds.maxLat - Number(point.latitude)) /
          (bounds.maxLat - bounds.minLat)) *
        100,
      unit: "%",
    };
  }
  const projected = projectLocation(point, mapState.zoom);
  return {
    x: clamp(projected.x - mapState.topLeft.x, 18, mapState.width - 18),
    y: clamp(projected.y - mapState.topLeft.y, 18, mapState.height - 18),
    unit: "px",
  };
}

function renderMarkers(locations) {
  markerLayer.replaceChildren();
  renderTiles(locations);
  if (!locations.length) {
    emptyNode.style.display = "block";
    return;
  }
  emptyNode.style.display = "none";
  const clusters = new Map();
  for (const point of locations) {
    const position = markerPosition(point);
    // Off-screen markers are omitted when zooming instead of pinned to the edge.
    const projected = projectLocation(point, mapState.zoom);
    if (
      projected.x < mapState.topLeft.x ||
      projected.x > mapState.topLeft.x + mapState.width ||
      projected.y < mapState.topLeft.y ||
      projected.y > mapState.topLeft.y + mapState.height
    )
      continue;
    let key = point.subject_id;
    if (point.provider === "camera") {
      for (const [candidate, members] of clusters) {
        if (members[0].provider !== "camera") continue;
        const anchor = markerPosition(members[0]);
        if (Math.hypot(position.x - anchor.x, position.y - anchor.y) < 46) {
          key = candidate;
          break;
        }
      }
    }
    if (!clusters.has(key)) clusters.set(key, []);
    clusters.get(key).push(point);
  }
  for (const points of clusters.values()) {
    const point = points[0];
    const position = markerPosition(point);
    const marker = document.createElement("button");
    marker.type = "button";
    marker.className = `location-marker${point.provider === "camera" ? " is-camera" : ""}${points.length > 1 ? " is-cluster" : ""}`;
    marker.style.left = `${position.x}px`;
    marker.style.top = `${position.y}px`;
    marker.title = points.map((p) => p.label).join(" · ");
    if (point.provider !== "camera" && point.stale) {
      marker.style.opacity = "0.5";
      marker.title += " · Last known position — stale or offline";
    }
    marker.setAttribute(
      "aria-label",
      points.length > 1
        ? `${points.length} camera views: ${marker.title}`
        : marker.title,
    );
    marker.textContent =
      point.provider === "camera" ? String(points.length) : point.label;
    marker.addEventListener("click", () => {
      selectedNames = points.map((p) => p.label);
      renderCameraBrowser();
      cameraBrowser.scrollIntoView({ behavior: "smooth", block: "nearest" });
    });
    markerLayer.append(marker);
  }
}

function renderList(locations) {
  listNode.replaceChildren();
  sortedLocations(locations).forEach((point) => {
    const item = document.createElement("article");
    item.className = "location-list-item";

    const header = document.createElement("header");
    const title = document.createElement("div");
    const name = document.createElement("strong");
    name.textContent = point.label || point.subject_id || "Location";
    const provider = document.createElement("small");
    provider.textContent = `${point.provider || "android"} - ${formatAge(
      point.age_seconds,
    )} ago`;
    title.append(name, provider);

    const pill = document.createElement("span");
    pill.className = `location-pill${point.stale ? " is-stale" : ""}`;
    pill.textContent = point.stale ? "last known" : "recent GPS";
    header.append(title, pill);

    const meta = document.createElement("div");
    meta.className = "location-meta-row";
    meta.textContent = `${formatNumber(point.latitude, 5)}, ${formatNumber(
      point.longitude,
      5,
    )} · ${formatNumber(point.accuracy_m, 0)}m accuracy`;

    item.append(header, meta);
    if (point.battery_percent !== null && point.battery_percent !== undefined) {
      const battery = document.createElement("div");
      battery.className = "location-battery";
      const fill = document.createElement("span");
      fill.style.width = `${Math.max(0, Math.min(100, point.battery_percent))}%`;
      battery.appendChild(fill);
      item.appendChild(battery);
    }
    listNode.appendChild(item);
  });
}

function renderStats(locations) {
  const stale = locations.filter((point) => point.stale).length;
  activeCountNode.textContent = String(locations.length - stale);
  staleCountNode.textContent = String(stale);
  providerCountNode.textContent = String(householdCount);
}

function render(locations) {
  lastLocations = locations;
  const validLocations = locations.filter(
    (point) =>
      Number.isFinite(Number(point.latitude)) &&
      Number.isFinite(Number(point.longitude)),
  );
  renderMarkers([...cameraPoints.filter(matchesCamera), ...validLocations]);
  renderCameraBrowser();
  renderList(validLocations);
  renderStats(validLocations);
}

async function refreshLocations() {
  if (refreshing) return;
  refreshing = true;
  const controller =
    typeof AbortController === "function" ? new AbortController() : null;
  const timeout = setTimeout(() => controller?.abort(), 8000);
  try {
    const response = await fetch("/api/nearby-context", {
      signal: controller?.signal,
      headers: { Accept: "application/json" },
      cache: "no-store",
    });
    if (!response.ok) throw new Error("Location refresh unavailable");
    const payload = await response.json();
    catalogCameras = payload.cameras || [];
    unmappedCameras = payload.unmapped_cameras || [];
    cameraPoints = catalogCameras.map((camera) => ({
      subject_id: `camera-${camera.name}`,
      label: camera.name,
      provider: "camera",
      latitude: camera.location.lat,
      longitude: camera.location.lon,
      live: camera.live,
      locationLabel: camera.location.label,
    }));
    const { mapLocations } = await freshnessModule;
    lastMapRefresh = new Date().toISOString();
    mapOffline = false;
    tilesMissing = false;
    await renderHousehold(payload);
    render(mapLocations(payload.locations || []));
    updateMapStatus();
  } catch (_error) {
    const { mapLocations } = await freshnessModule;
    mapOffline = true;
    render(mapLocations(lastLocations, true));
    updateMapStatus();
    // Keep the map but downgrade cached presence immediately on a failed poll.
    if (lastHouseholdPayload) {
      const { renderPresence } = await presenceModule;
      renderPresence(householdNode, lastHouseholdPayload, true);
    }
    // Keep the last rendered state if a dashboard refresh races a restart.
    let warning = document.getElementById("household-refresh-warning");
    if (!warning) {
      warning = document.createElement("p");
      warning.id = "household-refresh-warning";
      householdNode.prepend(warning);
    }
    warning.textContent =
      "Refresh delayed — displayed presence may be out of date.";
  } finally {
    clearTimeout(timeout);
    refreshing = false;
  }
}

const heading = document.querySelector(".location-map-header h1");
if (heading) heading.textContent = "Cameras, people & places";
const controls = document.createElement("div");
controls.className = "camera-map-controls";
const search = document.createElement("input");
search.type = "search";
search.placeholder = "Find a camera or place…";
search.setAttribute("aria-label", "Find a camera or place");
const area = document.createElement("select");
area.setAttribute("aria-label", "Map area");
for (const [value, label] of [
  ["all", "All locations"],
  ["chicago", "Chicago & suburbs"],
  ["wisconsin", "Wisconsin"],
  ["michigan", "Michigan shore"],
]) {
  const option = document.createElement("option");
  option.value = value;
  option.textContent = label;
  area.append(option);
}
controls.append(search, area);
for (const [label, delta] of [
  ["−", -1],
  ["+", 1],
  ["Fit", 0],
]) {
  const button = document.createElement("button");
  button.type = "button";
  button.textContent = label;
  button.setAttribute(
    "aria-label",
    label === "Fit"
      ? "Fit all visible cameras"
      : delta > 0
        ? "Zoom in"
        : "Zoom out",
  );
  button.addEventListener("click", () => {
    zoomDelta = delta ? clamp(zoomDelta + delta, -3, 10) : 0;
    render(lastLocations);
  });
  controls.append(button);
}
mapNode.before(controls);
const cameraBrowser = document.createElement("section");
cameraBrowser.className = "camera-browser";
cameraBrowser.setAttribute("aria-label", "Camera previews and map coverage");
document.querySelector(".location-dashboard").after(cameraBrowser);
function matchesCamera(point) {
  const query = search.value.trim().toLowerCase();
  const text =
    `${point.label || point.name} ${point.locationLabel || point.location?.label || ""}`.toLowerCase();
  if (query && !text.includes(query)) return false;
  const lat = point.latitude ?? point.location?.lat;
  const lon = point.longitude ?? point.location?.lon;
  return (
    area.value === "all" ||
    (area.value === "chicago" && lat < 42.5 && lon < -87) ||
    (area.value === "wisconsin" && lat >= 42.5 && lon < -87) ||
    (area.value === "michigan" && lon >= -87)
  );
}
function renderCameraBrowser() {
  cameraBrowser.replaceChildren();
  const shown = [...catalogCameras, ...unmappedCameras]
    .filter(matchesCamera)
    .filter((c) => !selectedNames.length || selectedNames.includes(c.name));
  const title = document.createElement("h2");
  title.textContent = `${shown.length} camera views${selectedNames.length ? " at selected marker" : ""}`;
  cameraBrowser.append(title);
  if (selectedNames.length) {
    const clear = document.createElement("button");
    clear.type = "button";
    clear.textContent = "Show all matching cameras";
    clear.addEventListener("click", () => {
      selectedNames = [];
      renderCameraBrowser();
    });
    cameraBrowser.append(clear);
  }
  const grid = document.createElement("div");
  grid.className = "camera-preview-grid";
  for (const camera of shown) {
    const card = document.createElement("a");
    card.className = "camera-preview-card";
    card.href = camera.live;
    const img = document.createElement("img");
    img.src = camera.image;
    img.alt = "";
    img.loading = "lazy";
    img.decoding = "async";
    const title = document.createElement("strong");
    title.textContent = camera.name;
    const location = document.createElement("span");
    location.textContent = camera.location
      ? `${camera.location.label} · ${camera.location.accuracy.replaceAll("_", " ")}`
      : "Location not verified yet";
    const status = document.createElement("small");
    freshnessModule.then(({ cameraMapStatus }) => {
      status.textContent = cameraMapStatus(camera);
    });
    card.append(img, title, location, status);
    grid.append(card);
  }
  cameraBrowser.append(grid);
}
for (const [node, event] of [
  [search, "input"],
  [area, "change"],
])
  node.addEventListener(event, () => {
    selectedNames = [];
    zoomDelta = 0;
    render(lastLocations);
  });

freshnessModule.then(({ mapLocations }) => {
  render(mapLocations(readInitialLocations()));
  updateMapStatus();
});
refreshLocations();
setInterval(refreshLocations, 15000);

let resizeTimer;
window.addEventListener("resize", () => {
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(() => render(lastLocations), 150);
});
for (const [node, label] of [
  [activeCountNode, "fresh GPS"],
  [staleCountNode, "stale GPS"],
  [providerCountNode, "presence sources"],
]) {
  const caption = node.parentElement.querySelector("small");
  if (caption) caption.textContent = label;
}
