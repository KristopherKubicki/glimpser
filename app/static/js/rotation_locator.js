export const LOCATOR_COLORS = [
  "#89d9ce",
  "#a8bdf4",
  "#e5ba81",
  "#d2a7de",
  "#a7ca87",
  "#e9a8a1",
];
export function shortCameraName(name) {
  return name
    .replace(/^Beach_?/, "")
    .replace(/_/g, " ")
    .replace(/([a-z])([A-Z])/g, "$1 $2");
}

// Context comes from the existing authorized dashboard catalog, never camera URLs.
export function locatorModel(catalogs, activeNames) {
  const active = new Set(activeNames);
  const groups = new Map();
  for (const model of catalogs) {
    if (!["property", "beach-conditions"].includes(model?.dashboard)) continue;
    for (const camera of model.cameras || []) {
      if (!camera?.name || !camera.group || camera.media_kind === "web")
        continue;
      if (!groups.has(camera.group)) groups.set(camera.group, new Map());
      groups.get(camera.group).set(camera.name, camera);
    }
  }
  const matches = [...groups].filter(([, cameras]) =>
    [...active].some((name) => cameras.has(name)),
  );
  // A mixed-site overview has no single honest location anchor.
  const complete = matches.filter(([, cameras]) =>
    [...active].every((name) => cameras.has(name)),
  );
  if (!active.size || !complete.length) return null;
  const [group, cameras] = complete.sort((a, b) => b[1].size - a[1].size)[0];
  const all = [...cameras.values()].sort((a, b) =>
    a.name.localeCompare(b.name),
  );
  const selected =
    all.length <= 12
      ? all
      : [
          ...all.filter((c) => active.has(c.name)),
          ...all.filter((c) => !active.has(c.name)),
        ]
          .slice(0, 12)
          .sort((a, b) => a.name.localeCompare(b.name));
  const valid = (c) =>
    Number.isFinite(c.location?.lat) &&
    Number.isFinite(c.location?.lon) &&
    Math.abs(c.location.lat) <= 85 &&
    Math.abs(c.location.lon) <= 180;
  let geographic = selected.length > 1 && selected.every(valid);
  const points = selected.map((c, index) => ({
    color: LOCATOR_COLORS[index % LOCATOR_COLORS.length],
    number: index + 1,
    name: c.name,
    active: active.has(c.name),
    held: Boolean(c.issue),
  }));
  if (geographic) {
    const latitude =
      selected.reduce((sum, c) => sum + c.location.lat, 0) / selected.length;
    const xs = selected.map(
      (c) => c.location.lon * Math.cos((latitude * Math.PI) / 180),
    );
    const ys = selected.map((c) => -c.location.lat);
    const minX = Math.min(...xs),
      minY = Math.min(...ys);
    const spanX = Math.max(...xs) - minX,
      spanY = Math.max(...ys) - minY;
    // Co-located/rounded property coordinates cannot describe camera placement.
    geographic = Math.max(spanX, spanY) > 0.0001;
    if (geographic) {
      const scale = Math.max(spanX / 180, spanY / 70);
      points.forEach((p, i) => {
        p.x = 20 + (180 - spanX / scale) / 2 + (xs[i] - minX) / scale;
        p.y = 20 + (70 - spanY / scale) / 2 + (ys[i] - minY) / scale;
      });
    }
  }
  if (!geographic)
    points.forEach((p, i) => {
      p.x = 38 + (i % 3) * 72;
      p.y = 16 + Math.floor(i / 3) * 26;
    });
  return {
    group,
    geographic,
    points,
    active: selected.filter((c) => active.has(c.name)).map((c) => c.name),
    total: all.length,
    height: geographic ? 110 : Math.ceil(points.length / 3) * 26 + 12,
  };
}

export function mountRotationLocator(stage, catalogs, profile) {
  if (!["office", "living"].includes(profile)) return { dispose() {} };
  const panel = document.createElement("aside");
  panel.className = "rotation-locator";
  panel.setAttribute("aria-label", "Current camera location context");
  panel.hidden = true;
  stage.append(panel);
  let signature = "";
  const svgElement = (tag, attributes) => {
    const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
    for (const [key, value] of Object.entries(attributes))
      node.setAttribute(key, String(value));
    return node;
  };
  const update = () => {
    const overview = stage.querySelector(".rotation-overview");
    const names = overview
      ? [...overview.querySelectorAll(".rotation-overview-tile")].map(
          (tile) => tile.dataset.heroName,
        )
      : [
          stage.querySelector(".landing-scene.is-visible")?.dataset.heroName,
        ].filter(Boolean);
    const model = locatorModel(catalogs(), names);
    // Match the quiet marker key to the actual overview tiles. The source name
    // remains the identity; no inferred geographical position is used here.
    const keys = new Map((model?.points || []).map((p) => [p.name, p]));
    stage.querySelectorAll(".rotation-overview-tile").forEach((tile) => {
      const point = keys.get(tile.dataset.heroName);
      let key = tile.querySelector("[data-locator-key]");
      if (!point) {
        key?.remove();
        return;
      }
      const label = tile.querySelector(".rotation-overview-label");
      if (!label) return;
      if (!key) {
        key = document.createElement("span");
        key.dataset.locatorKey = "";
        key.className = "rotation-locator-key";
        label.prepend(key);
      }
      key.textContent = String(point.number);
      key.style.setProperty("--locator-key-color", point.color);
      key.setAttribute("aria-label", `Locator camera ${point.number}`);
    });
    const next = JSON.stringify(model);
    if (next === signature) return;
    signature = next;
    panel.replaceChildren();
    panel.hidden = !model;
    if (!model) return;
    const heading = document.createElement("div");
    heading.className = "rotation-locator-heading";
    heading.textContent = model.group.replace(/ property health$/, "");
    const svg = svgElement("svg", {
      viewBox: `0 0 220 ${model.height}`,
      "aria-hidden": "true",
    });
    model.points.forEach((p) => {
      const dot = svgElement("circle", {
        cx: p.x,
        cy: p.y,
        r: p.active ? 8 : 5,
        class: p.active ? "locator-active" : p.held ? "locator-held" : "",
      });
      dot.style.setProperty("--locator-key-color", p.color);
      if (p.held) dot.classList.add("locator-held-source");
      const title = svgElement("title", {});
      title.textContent = `${p.name}${p.held ? " · source needs attention" : ""}`;
      dot.append(title);
      svg.append(dot);
      if (p.active) {
        const key = svgElement("text", {
          x: p.x,
          y: p.y + 3,
          "text-anchor": "middle",
          class: "locator-marker-key",
        });
        key.textContent = String(p.number);
        svg.append(key);
      }
      if (!model.geographic) {
        const number = svgElement("text", {
          x: p.x,
          y: p.y + 14,
          "text-anchor": "middle",
        });
        const label = shortCameraName(p.name);
        number.textContent =
          label.length > 13 ? label.slice(0, 12) + "…" : label;
        svg.append(number);
      }
    });
    const caption = document.createElement("div");
    caption.className = "rotation-locator-caption";
    caption.textContent =
      model.active.length > 1
        ? `${model.active.length} highlighted views`
        : model.active.map(shortCameraName).join("");
    const note = document.createElement("small");
    note.textContent = model.geographic
      ? "Recorded positions · N ↑"
      : "Camera index · positions not mapped";
    if (model.total > model.points.length)
      note.textContent += ` · ${model.points.length}/${model.total} views`;
    panel.append(heading, svg, caption, note);
  };
  update();
  // A bounded poll avoids reacting to every video frame or DOM mutation.
  const timer = window.setInterval(update, 1000);
  return {
    dispose() {
      window.clearInterval(timer);
      panel.remove();
      stage
        .querySelectorAll("[data-locator-key]")
        .forEach((key) => key.remove());
    },
  };
}
