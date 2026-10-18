import {
  captureImageUrl,
  captureAge,
  sourceAge,
  sourceNeedsAttention,
} from "./capture_age.js";

export async function fetchOverviewCatalogs(signal) {
  return Promise.all(
    ["arrivals", "property", "beach-conditions", "growers", "regional"].map(
      async (dashboard) => {
        try {
          const response = await fetch(`/dashboard/${dashboard}/data`, {
            cache: "no-store",
            signal,
          });
          if (!response.ok) return null;
          const model = await response.json();
          return Array.isArray(model?.cameras) ? model : null;
        } catch {
          return null;
        }
      },
    ),
  );
}

export function chooseOverview(scenes, catalogs, isSuppressed, offset = 0) {
  const byName = new Map(scenes.map((s) => [s.dataset.heroName, s]));
  const groups = new Map();
  for (const model of catalogs) {
    for (const camera of model.cameras || []) {
      if (!camera.group || camera.group === "Other views") continue;
      const scene = byName.get(camera.name);
      if (
        !scene ||
        camera.issue ||
        sourceNeedsAttention(camera.freshness) ||
        isSuppressed(scene) ||
        !scene.dataset.heroImageUrl
      )
        continue;
      const key = `${model.dashboard}: ${camera.group}`;
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push({
        name: camera.name,
        freshness: camera.freshness || {},
        image: scene.dataset.heroImageUrl,
        captured: scene.dataset.heroLastScreenshotTime || camera.captured,
        caption:
          scene.querySelector(".kiosk-caption-text")?.textContent.trim() ||
          camera.caption ||
          "",
        live: scene.dataset.heroLiveUrl || camera.live,
        scene,
      });
    }
  }
  const eligible = [...groups.entries()].filter(
    ([, cameras]) => cameras.length >= 2,
  );
  if (!eligible.length) return null;
  const [label, cameras] = eligible[offset % eligible.length];
  // Rotate through larger groups so the same first four do not monopolize overviews.
  const start = (Math.floor(offset / eligible.length) * 4) % cameras.length;
  const ordered = [...cameras.slice(start), ...cameras.slice(0, start)];
  return {
    label: label.split(": ").slice(1).join(": "),
    cameras: ordered.slice(0, ordered.length >= 4 ? 4 : 2),
  };
}

export function createOverview(selection, host, onReady, onFinish) {
  const node = document.createElement("section");
  node.className = "rotation-overview";
  node.setAttribute("aria-label", `${selection.label} camera overview`);
  const heading = document.createElement("header");
  const title = document.createElement("strong");
  title.textContent = selection.title || `${selection.label} · Camera overview`;
  const remaining = document.createElement("span");
  heading.append(title, remaining);
  if (selection.title) {
    const resume = document.createElement("button");
    resume.type = "button";
    resume.textContent = "Resume rotation";
    resume.addEventListener("click", () => finish());
    heading.append(resume);
  }
  const grid = document.createElement("div");
  grid.className = "rotation-overview-grid";
  node.append(heading, grid);
  let disposed = false,
    completed = 0,
    ageTimer = null,
    durationTimer = null;
  const timers = [],
    records = [];
  const dispose = () => {
    disposed = true;
    timers.forEach(window.clearTimeout);
    window.clearInterval(ageTimer);
    window.clearTimeout(durationTimer);
    records.forEach((r) => {
      r.image.onload = null;
      r.image.onerror = null;
    });
    node.remove();
  };
  const finish = () => {
    if (disposed) return;
    dispose();
    onFinish();
  };
  const finalize = () => {
    if (disposed || completed !== selection.cameras.length) return;
    const good = records.filter((r) => r.loaded);
    if (good.length < 2) {
      finish();
      return;
    }
    const tiles = good.slice(0, selection.title ? 4 : good.length >= 4 ? 4 : 2);
    node.classList.add(tiles.length >= 3 ? "is-four" : "is-two");
    tiles.forEach((r) => grid.append(r.tile));
    host.append(node);
    const duration = Math.min(30000, selection.duration || 20000);
    const deadline = Date.now() + duration;
    const tick = () => {
      remaining.textContent = `Rotation resumes in ${Math.max(0, Math.ceil((deadline - Date.now()) / 1000))}s`;
      tiles.forEach((r) => {
        r.age.textContent = `Captured ${captureAge(r.camera.captured)}`;
        r.source.textContent = sourceAge(r.camera.freshness);
      });
    };
    tick();
    ageTimer = window.setInterval(tick, 1000);
    durationTimer = window.setTimeout(finish, duration);
    onReady();
  };
  selection.cameras.forEach((camera) => {
    const tile = document.createElement("a");
    tile.className = "rotation-overview-tile";
    tile.href = camera.live;
    const image = document.createElement("img");
    image.alt = `${camera.name} latest capture`;
    const label = document.createElement("div");
    label.className = "rotation-overview-label";
    const name = document.createElement("strong");
    name.textContent = camera.name;
    const age = document.createElement("span");
    age.textContent = captureAge(camera.captured);
    label.append(name, age);
    const caption = document.createElement("p");
    caption.className = "rotation-overview-caption";
    caption.textContent = camera.caption;
    const source = document.createElement("p");
    source.className = "rotation-overview-source";
    source.classList.toggle(
      "is-source-older",
      sourceNeedsAttention(camera.freshness),
    );
    source.textContent = sourceAge(camera.freshness);
    tile.append(image, label, source, caption);
    const record = { tile, image, age, source, camera, loaded: false };
    records.push(record);
    let settled = false;
    const settle = (loaded) => {
      if (disposed || settled) return;
      settled = true;
      record.loaded = loaded;
      completed++;
      finalize();
    };
    image.onload = () => settle(image.naturalWidth > 0);
    image.onerror = () => settle(false);
    timers.push(window.setTimeout(() => settle(false), 8000));
    image.src = captureImageUrl(camera.image, camera.captured);
  });
  return { dispose, cameras: selection.cameras };
}
