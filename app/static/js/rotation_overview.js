import { prepareSceneComfort } from "./room_comfort.js?v=20261009-night-clamp";
import {
  captureImageUrl,
  captureAge,
  sourceAge,
  sourceNeedsAttention,
} from "./capture_age.js";
import {
  livePilotEligible,
  liveStreamLimit,
  mountKioskLive,
} from "./kiosk_live.js?v=20261017-media-lifecycle";

const HOUSE_OVERVIEW_GROUPS = new Set([
  "Knox arrivals",
  "Beach arrivals",
  "Knox property health",
  "Beach property health",
  "At the Beach house",
  "Approaches",
  "Around the home",
]);
const HOUSE_EXTERIOR_ORDER = [
  "ArgyleEntryFisheye",
  "FrontDoor",
  "Driveway",
  "Street",
  "Garage",
  "Walkway",
  "Backyard",
  "Garden",
  "BeachDriveway",
  "BeachPathway",
  "BeachFrontYard",
  "BeachSouthJetty",
  "BeachShore",
  "BeachMapleTree",
];
const HOUSE_GROUP_ORDER = [
  "Knox arrivals",
  "Beach property health",
  "Beach arrivals",
  "Around the home",
  "Approaches",
  "At the Beach house",
];

function houseOverviewCycle(houses) {
  const byGroup = new Map(houses.map((entry) => [entry[1][0].group, entry]));
  const property = byGroup.get("Knox property health");
  const otherHouses = [
    ...HOUSE_GROUP_ORDER.map((group) => byGroup.get(group)).filter(Boolean),
    ...houses.filter(
      (entry) =>
        entry !== property && !HOUSE_GROUP_ORDER.includes(entry[1][0].group),
    ),
  ];
  if (!property) return otherHouses;
  if (!otherHouses.length) return [property];
  const cycle = [];
  otherHouses.forEach((entry, index) => {
    if (index % 2 === 0) cycle.push(property);
    cycle.push(entry);
  });
  return cycle;
}

async function fetchOverviewCatalog(dashboard, signal) {
  if (signal?.aborted) return null;
  const controller =
    typeof AbortController === "function" ? new AbortController() : null;
  let interrupted = false,
    timer,
    cancel;
  const deadline = new Promise((_, reject) => {
    cancel = () => {
      interrupted = true;
      reject(new Error("Catalog refresh interrupted"));
      controller?.abort();
    };
    timer = window.setTimeout(cancel, 8000);
    signal?.addEventListener("abort", cancel, { once: true });
  });
  try {
    // Bound headers AND body decoding. Abort alone cannot release Promise.all
    // when a transport ignores it; one failed source must not stop the cycle.
    const model = await Promise.race([
      (async () => {
        const response = await fetch(
          dashboard === "local-tv"
            ? "/feed-tv/data"
            : `/dashboard/${dashboard}/data`,
          { cache: "no-store", signal: controller?.signal || signal },
        );
        if (interrupted || !response.ok) return null;
        return response.json();
      })(),
      deadline,
    ]);
    if (interrupted) return null;
    if (dashboard === "local-tv")
      return Array.isArray(model?.clips)
        ? { dashboard, cameras: [], clips: model.clips }
        : null;
    if (!Array.isArray(model?.cameras)) return null;
    return {
      ...model,
      dashboard,
      cameras: model.cameras.filter(
        (camera) =>
          camera && typeof camera.name === "string" && camera.name.trim(),
      ),
    };
  } catch {
    return null;
  } finally {
    window.clearTimeout(timer);
    signal?.removeEventListener("abort", cancel);
  }
}

export async function fetchOverviewCatalogs(signal) {
  return Promise.all(
    [
      "arrivals",
      "property",
      "stores",
      "area",
      "security",
      "beach-conditions",
      "growers",
      "regional",
      "energy",
      "transportation",
      "water",
      "conditions",
      "local-tv",
    ].map((dashboard) => fetchOverviewCatalog(dashboard, signal)),
  );
}

export function isPortraitFrame(image) {
  return Boolean(
    image?.naturalWidth > 0 &&
      image?.naturalHeight > 0 &&
      image.naturalWidth / image.naturalHeight < 0.85,
  );
}

function pairCoverage(first, second, viewport) {
  const frames = [first, second].map((camera) =>
    camera.scene?.querySelector(".landing-hero-media img"),
  );
  if (
    frames.some(
      (frame) => !(frame?.naturalWidth > 0 && frame?.naturalHeight > 0),
    )
  )
    return -1;
  const width = viewport?.innerWidth || 1280;
  const height = Math.max(
    1,
    (viewport?.innerHeight || 720) - (width <= 700 ? 60 : 76),
  );
  const ratios = frames.map(
    (frame) => frame.naturalWidth / frame.naturalHeight,
  );
  const mixed = isPortraitFrame(frames[0]) !== isPortraitFrame(frames[1]);
  // Match the existing CSS slots. Score contained picture area, not a crop;
  // mobile stacks both tiles, while a desktop mixed pair uses 1:3 columns.
  return ratios.reduce((total, ratio, index) => {
    const tileWidth =
      width <= 700
        ? width
        : width * (mixed ? (index === 0 ? 0.25 : 0.75) : 0.5);
    const tileHeight = width <= 700 ? height / 2 : height;
    const pictureHeight = Math.min(tileHeight, tileWidth / ratio);
    return total + (pictureHeight * pictureHeight * ratio) / (width * height);
  }, 0);
}

export function spaceAwareCameras(
  cameras,
  visit,
  viewport = globalThis.window,
) {
  // A tall portrait beside two landscapes uses the existing three-tile layout.
  // Keep a full four-up every cycle so optimizing space does not hide a feed.
  if (
    visit % 3 === 2 &&
    cameras.length >= 4 &&
    viewport?.innerWidth / viewport?.innerHeight >= 1.5
  ) {
    const firstFour = cameras.slice(0, 4);
    const frames = firstFour.map((camera) =>
      camera.scene?.querySelector(".landing-hero-media img"),
    );
    if (
      frames.filter(isPortraitFrame).length === 1 &&
      frames.every(
        (frame) =>
          frame?.naturalWidth > 0 &&
          frame?.naturalHeight > 0 &&
          (isPortraitFrame(frame) ||
            (frame.naturalWidth / frame.naturalHeight >= 1.4 &&
              frame.naturalWidth / frame.naturalHeight <= 2)),
      )
    ) {
      const portrait = firstFour.find((_, index) =>
        isPortraitFrame(frames[index]),
      );
      return [
        portrait,
        ...firstFour.filter((camera) => camera !== portrait).slice(0, 2),
      ];
    }
  }
  if (visit % 3 !== 1 || cameras.length < 3) return cameras.slice(0, 4);
  const portraits = cameras.filter((camera) =>
    isPortraitFrame(camera.scene?.querySelector(".landing-hero-media img")),
  );
  if (!portraits.length) {
    const known = cameras.filter((camera) => {
      const frame = camera.scene?.querySelector(".landing-hero-media img");
      return frame?.naturalWidth > 0 && frame?.naturalHeight > 0;
    });
    if (known.length < 2) return cameras.slice(0, 4);
    // Give landscape groups a closer two-up every third visit as well. Advance
    // within the ranked window so four-camera groups do not always pair A/B.
    const start = (Math.floor(visit / 3) * 2) % known.length;
    return [known[start], known[(start + 1) % known.length]];
  }
  const first = portraits[0];
  let second = portraits[1] || cameras.find((camera) => camera !== first);
  let best = pairCoverage(first, second, viewport);
  for (const candidate of cameras) {
    if (candidate === first) continue;
    const coverage = pairCoverage(first, candidate, viewport);
    // Keep the established order for ties and tiny measurement differences.
    if (coverage > best + 0.03) {
      second = candidate;
      best = coverage;
    }
  }
  return [first, second];
}

export function overviewGeometry(images, viewport = globalThis.window) {
  // Compare contained picture area: never trade away image edges to fill a tile.
  // Keep narrow-screen CSS stacking and existing mixed-portrait layouts intact.
  const width = viewport?.innerWidth || 1280;
  const height = Math.max(1, (viewport?.innerHeight || 720) - 76);
  if (
    images.length === 2 &&
    width > 700 &&
    images.every(
      (image) =>
        image?.naturalWidth > 0 &&
        image?.naturalHeight > 0 &&
        image.naturalWidth >= image.naturalHeight,
    )
  ) {
    const area = (tileWidth, tileHeight) =>
      images.reduce((sum, image) => {
        const ratio = image.naturalWidth / image.naturalHeight;
        const pictureHeight = Math.min(tileHeight, tileWidth / ratio);
        return sum + pictureHeight * pictureHeight * ratio;
      }, 0);
    // Match the grid's four-pixel gutter and avoid marginal layout changes.
    if (area(width, (height - 4) / 2) > area((width - 4) / 2, height) * 1.1)
      return "landscape-stacked";
  }
  const portraits = images.map(isPortraitFrame);
  if (images.length === 2 && portraits[0] !== portraits[1])
    return portraits[0] ? "portrait-left" : "portrait-right";
  if (images.length === 3 && portraits.filter(Boolean).length === 1)
    return "portrait-tall";
  return "balanced";
}

export function chooseOverview(
  scenes,
  catalogs,
  isSuppressed,
  offset = 0,
  profile = "office",
  recentlyViewed = () => false,
) {
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
      if (groups.get(key).some((entry) => entry.name === camera.name)) continue;
      groups.get(key).push({
        name: camera.name,
        group: camera.group,
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
  const houses = eligible.filter(([, cameras]) =>
    HOUSE_OVERVIEW_GROUPS.has(cameras[0].group),
  );
  const others = eligible.filter(
    ([, cameras]) => !HOUSE_OVERVIEW_GROUPS.has(cameras[0].group),
  );
  const alternate =
    ["office", "living"].includes(profile) && houses.length && others.length;
  const houseCycle = houseOverviewCycle(houses);
  let lane = alternate
    ? offset % 2 === 0 || !others.length
      ? houseCycle
      : others
    : ["office", "living"].includes(profile) && houses.length
      ? houseCycle
      : eligible;
  let turn = alternate ? Math.floor(offset / 2) : offset;
  if (profile === "office") {
    const knox = eligible.filter(([, cameras]) =>
      ["Knox arrivals", "Knox property health"].includes(cameras[0].group),
    );
    const rest = eligible.filter((entry) => !knox.includes(entry));
    if (knox.length && rest.length) {
      // Half of office overview visits return home; the other half retains
      // every other eligible board. Expand complete cycles for window fairness.
      lane = [];
      for (let i = 0; i < knox.length * rest.length; i++) {
        lane.push(knox[i % knox.length], rest[i % rest.length]);
      }
      turn = offset;
    }
  }
  if (["office", "living"].includes(profile)) {
    const beach = eligible.filter(([, cameras]) =>
      [
        "Beach arrivals",
        "Beach property health",
        "At the Beach house",
      ].includes(cameras[0].group),
    );
    const home = eligible.filter(([, cameras]) =>
      ["Knox arrivals", "Knox property health"].includes(cameras[0].group),
    );
    const other = eligible.filter(
      (entry) => !beach.includes(entry) && !home.includes(entry),
    );
    const rest = other.length ? other : home;
    const anchors = home.length ? home : rest;
    if (beach.length && rest.length) {
      // Two of five comparison visits belong to the owner's beach. Rotate
      // complete windows within each group instead of repeating one camera.
      lane = [];
      for (let i = 0; i < beach.length * anchors.length * rest.length; i++) {
        lane.push(
          beach[(i * 2) % beach.length],
          anchors[(i * 2) % anchors.length],
          beach[(i * 2 + 1) % beach.length],
          anchors[(i * 2 + 1) % anchors.length],
          rest[i % rest.length],
        );
      }
      turn = offset;
    }
  }
  if (profile === "office") {
    const argyle = eligible.filter(([, cameras]) =>
      ["Argyle arrivals", "Argyle showroom"].includes(cameras[0].group),
    );
    const halsted = eligible.filter(
      ([, cameras]) => cameras[0].group === "Halsted activity",
    );
    // Share by property first: Argyle having two boards must not halve
    // Halsted's coverage. Each site's own boards advance independently.
    const stores = [];
    if (argyle.length && halsted.length) {
      for (let i = 0; i < argyle.length * halsted.length; i++)
        stores.push(argyle[i % argyle.length], halsted[i % halsted.length]);
    } else stores.push(...argyle, ...halsted);
    if (stores.length) {
      const beach = eligible.filter(([, cameras]) =>
        [
          "Beach arrivals",
          "Beach property health",
          "At the Beach house",
        ].includes(cameras[0].group),
      );
      const home = eligible.filter(([, cameras]) =>
        ["Knox arrivals", "Knox property health"].includes(cameras[0].group),
      );
      const other = eligible.filter(
        (entry) =>
          !stores.includes(entry) &&
          !beach.includes(entry) &&
          !home.includes(entry),
      );
      const fallback = other.length ? other : home.length ? home : beach;
      if (fallback.length) {
        const shores = beach.length ? beach : fallback;
        const homes = home.length ? home : fallback;
        lane = [];
        for (
          let i = 0;
          i < shores.length * homes.length * stores.length * fallback.length;
          i++
        ) {
          // Retain two beach turns in five; give stores a protected turn
          // and retain the full broader catalog instead of crowding it out.
          lane.push(
            shores[(i * 2) % shores.length],
            homes[i % homes.length],
            shores[(i * 2 + 1) % shores.length],
            stores[i % stores.length],
            fallback[i % fallback.length],
          );
        }
      } else lane = stores;
      turn = offset;
    }
  }
  const [label, cameras] = lane[turn % lane.length];
  const house = HOUSE_OVERVIEW_GROUPS.has(cameras[0].group);
  const argyleOrder = [
    "Front_door_doorbell",
    "Argyle100",
    "ArgyleEntryFisheye",
    "Showroom_Entrance",
  ];
  const ranked =
    cameras[0].group === "Argyle arrivals"
      ? [...cameras].sort((a, b) => {
          const rank = (camera) => {
            const index = argyleOrder.indexOf(camera.name);
            return index < 0 ? argyleOrder.length : index;
          };
          return rank(a) - rank(b);
        })
      : house
        ? [...cameras].sort(
            (a, b) =>
              (HOUSE_EXTERIOR_ORDER.indexOf(a.name) < 0
                ? 100
                : HOUSE_EXTERIOR_ORDER.indexOf(a.name)) -
              (HOUSE_EXTERIOR_ORDER.indexOf(b.name) < 0
                ? 100
                : HOUSE_EXTERIOR_ORDER.indexOf(b.name)),
          )
        : cameras;
  // Weighted groups still advance their four-camera window on every visit.
  const groupVisits =
    Math.floor(turn / lane.length) *
      lane.filter(([key]) => key === label).length +
    lane.slice(0, turn % lane.length).filter(([key]) => key === label).length;
  const start = (groupVisits * 4) % ranked.length;
  let window = [...ranked.slice(start), ...ranked.slice(0, start)];
  if (cameras[0].group === "Argyle arrivals") {
    const anchors = ranked.filter((camera) =>
      argyleOrder.slice(0, 2).includes(camera.name),
    );
    const companions = ranked.filter((camera) => !anchors.includes(camera));
    const companionStart =
      (groupVisits * (4 - anchors.length)) % (companions.length || 1);
    window = [
      ...anchors,
      ...companions.slice(companionStart),
      ...companions.slice(0, companionStart),
    ];
  }
  // Catalogs overlap: a camera shown on another board or full-screen should
  // yield to unseen alternatives here. Stable partition preserves the rotating
  // window within each tier, and never removes the only healthy choices.
  // Argyle arrivals keeps its deliberate Nest/exterior-first sequence.
  const ordered =
    cameras[0].group === "Argyle arrivals"
      ? window
      : window
          .map((camera) => ({
            camera,
            recent: Boolean(recentlyViewed(camera.name)),
          }))
          .sort((a, b) => Number(a.recent) - Number(b.recent))
          .map(({ camera }) => camera);
  return {
    label: label.split(": ").slice(1).join(": "),
    cameras:
      cameras[0].group === "Argyle arrivals"
        ? ordered.slice(0, 4)
        : spaceAwareCameras(ordered, groupVisits),
    // Argyle approaches should lead with Nest/exterior live video on each visit.
    // Interior tiles remain visible and can take over when exterior streams fail.
    liveOffset: cameras[0].group === "Argyle arrivals" ? 0 : groupVisits,
    duration: house || cameras[0].group === "Argyle arrivals" ? 30000 : 20000,
    profile,
    storeVisit:
      profile === "office" &&
      ["Argyle arrivals", "Argyle showroom", "Halsted activity"].includes(
        cameras[0].group,
      ),
  };
}

// Alternate a mixed camera/TV board with a TV-only surf board. Knox's
// even-numbered visits stay intact; only two tuner streams can run at once.
export function withOfficeTelevision(
  selection,
  scenes,
  isSuppressed,
  offset,
  profile,
) {
  if (profile !== "office" || offset % 4 !== 1 || selection?.storeVisit)
    return selection;
  if (selection?.cameras?.some((camera) => camera.name.startsWith("Beach")))
    return selection;
  const stations = scenes.filter(
    (scene) =>
      scene.dataset.heroMediaKind === "tv" &&
      scene.dataset.heroImageUrl &&
      !isSuppressed(scene),
  );
  const asCamera = (scene) => ({
    name: scene.dataset.heroName,
    scene,
    image: scene.dataset.heroImageUrl,
    captured: scene.dataset.heroLastScreenshotTime,
    live: scene.dataset.heroLiveUrl,
    freshness: {},
    caption: "Live television may include advertising",
  });
  if (offset % 8 === 5 && stations.length >= 4) {
    const order = ["WBBM-TV", "WMAQ", "WLS", "WFLD", "WGN"];
    const ranked = [...stations].sort((a, b) => {
      const rank = (scene) => {
        const i = order.indexOf(scene.dataset.heroName);
        return i < 0 ? 100 : i;
      };
      return rank(a) - rank(b);
    });
    return {
      label: "TV surf · Chicago stations",
      cameras: ranked.slice(0, 4).map(asCamera),
      // Alternate the active pair without requesting four physical tuners.
      liveOffset: (Math.floor(offset / 8) * 2) % 4,
      duration: 30000,
      profile,
    };
  }
  const liveStations = stations.filter((scene) =>
    livePilotEligible(scene, profile),
  );
  if (!selection || !liveStations.length) return selection;
  const camera = asCamera(
    liveStations[
      Math.floor(offset / (stations.length >= 4 ? 8 : 4)) % liveStations.length
    ],
  );
  const companions = selection.cameras
    .filter((item) => item.scene?.dataset.heroMediaKind !== "tv")
    .slice(0, 3);
  if (companions.length !== 3) return selection;
  return {
    ...selection,
    label: `${selection.label} · TV`,
    cameras: [camera, ...companions],
    liveOffset: 0,
    duration: 30000,
  };
}

export const overviewLiveLimit = liveStreamLimit;

// Preserve the existing fairness/health queue; only consider its next few views.
export function overviewFollowupIndex(queue, scenes, names, current) {
  const related = new Set(names);
  return (
    queue
      .slice(0, 4)
      .find(
        (index) =>
          index !== current && related.has(scenes[index]?.dataset.heroName),
      ) ?? -1
  );
}

export function overviewFadeDuration(value) {
  const match = String(value || "")
    .trim()
    .match(/^(\d+(?:\.\d+)?|\.\d+)(ms|s)$/);
  if (!match) return 1800;
  const duration = Number(match[1]) * (match[2] === "s" ? 1000 : 1);
  return Number.isFinite(duration) ? duration : 1800;
}

export function createOverview(selection, host, onReady, onFinish) {
  const node = document.createElement("section");
  node.className = "rotation-overview";
  node.setAttribute("aria-label", `${selection.label} camera overview`);
  const heading = document.createElement("header");
  const title = document.createElement("strong");
  title.textContent = selection.title || selection.label;
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
    finishing = false,
    completed = 0,
    ageTimer = null,
    durationTimer = null;
  let setHeld = () => false;
  const timers = [],
    records = [],
    liveHandles = [];
  const dispose = () => {
    if (disposed) return;
    disposed = true;
    window.removeEventListener("pagehide", dispose);
    liveHandles.forEach((handle) => handle.dispose());
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
    if (disposed || finishing) return;
    finishing = true;
    window.clearInterval(ageTimer);
    window.clearTimeout(durationTimer);
    const names = records.filter((r) => r.loaded).map((r) => r.camera.name);
    if (!node.parentNode) {
      dispose();
      onFinish([]);
      return;
    }
    // Keep the outgoing pictures/streams alive over the incoming scene. Never
    // remove the overview first and expose an unrelated stale frame underneath.
    const reduced = window.matchMedia?.(
      "(prefers-reduced-motion: reduce)",
    ).matches;
    const roomFade =
      getComputedStyle(host).getPropertyValue("--room-crossfade");
    const duration = reduced ? 600 : overviewFadeDuration(roomFade);
    node.classList.add("is-leaving");
    node.setAttribute("aria-hidden", "true");
    timers.push(window.setTimeout(dispose, duration + 100));
    onFinish(names);
  };
  const finalize = () => {
    if (disposed || completed !== selection.cameras.length) return;
    const good = records.filter((r) => r.loaded);
    if (good.length < 2) {
      finish();
      return;
    }
    const tiles = good.slice(0, 4);
    node.classList.add(tiles.length >= 3 ? "is-four" : "is-two");
    if (tiles.length === 3) node.classList.add("is-three");
    // Decide once from loaded stills; video startup must not rearrange tiles.
    const geometry = overviewGeometry(tiles.map((record) => record.image));
    node.classList.add(`geometry-${geometry}`);
    if (geometry === "portrait-tall")
      tiles
        .find((record) => isPortraitFrame(record.image))
        .tile.classList.add("is-portrait-primary");
    tiles.forEach((r) => grid.append(r.tile));
    // A broadcast board must earn its turn with playing frames. Keep the
    // outgoing scene visible while decoders warm; saved-only boards show now.
    const eligible = tiles.filter((record) =>
      livePilotEligible(record.camera.scene, selection.profile),
    );
    const deferBroadcast =
      !selection.title &&
      eligible.some((record) =>
        ["youtube", "tv"].includes(record.camera.scene.dataset.heroMediaKind),
      );
    let shownAt = null,
      heldAt = null;
    const duration = Math.min(30000, selection.duration || 20000);
    let deadline = 0;
    const tick = () => {
      remaining.textContent =
        heldAt !== null
          ? "Held"
          : `${Math.max(0, Math.ceil((deadline - Date.now()) / 1000))}s`;
      tiles.forEach((r) => {
        r.age.textContent = r.liveReady
          ? "LIVE"
          : `${r.buffering ? "Buffering · " : ""}Captured ${captureAge(r.camera.captured)}`;
        r.tile.title = [sourceAge(r.camera.freshness), r.camera.caption]
          .filter(Boolean)
          .join(" · ");
      });
    };
    setHeld = (held) => {
      // Warming broadcasts retain their startup deadline; only a visible board
      // can be held. Pause the viewing clock, not its playing camera streams.
      if (disposed || finishing || shownAt === null) return false;
      if (held && heldAt === null) {
        heldAt = Date.now();
        window.clearTimeout(durationTimer);
      } else if (!held && heldAt !== null) {
        const elapsed = Date.now() - heldAt;
        shownAt += elapsed;
        deadline += elapsed;
        tiles.forEach((record) => {
          if (record.liveDeadline) record.liveDeadline += elapsed;
        });
        heldAt = null;
        durationTimer = window.setTimeout(
          finish,
          Math.max(0, deadline - Date.now()),
        );
      }
      tick();
      return true;
    };
    const showBoard = () => {
      if (shownAt !== null || disposed || finishing) return;
      shownAt = Date.now();
      deadline = shownAt + duration;
      host.append(node);
      tick();
      ageTimer = window.setInterval(tick, 1000);
      window.clearTimeout(durationTimer);
      durationTimer = window.setTimeout(finish, duration);
      onReady();
    };
    if (deferBroadcast) durationTimer = window.setTimeout(finish, 36000);
    else showBoard();
    const liveLimit = selection.title ? 1 : overviewLiveLimit();
    // Advance even when exactly four cameras keep the same tile positions.
    // Alerts retain their first camera; routine boards share the live slots.
    const offset = selection.title
      ? 0
      : Math.max(0, Math.floor(selection.liveOffset || 0)) %
        (eligible.length || 1);
    const liveQueue = [...eligible.slice(offset), ...eligible.slice(0, offset)];
    let nextLive = 0;
    let activeLive = 0;
    const scheduleViewing = () => {
      if (shownAt === null) return;
      if (selection.title && !(selection.duration >= 30000)) return;
      // Only playing streams earn viewing time. Startup consumes no airtime.
      const nextDeadline = Math.min(
        shownAt + 60000,
        Math.max(shownAt + duration, ...tiles.map((r) => r.liveDeadline || 0)),
      );
      if (nextDeadline === deadline) return;
      deadline = nextDeadline;
      window.clearTimeout(durationTimer);
      if (heldAt === null)
        durationTimer = window.setTimeout(
          finish,
          Math.max(0, deadline - Date.now()),
        );
      tick();
    };
    const startLive = () => {
      while (
        !disposed &&
        !finishing &&
        activeLive < liveLimit &&
        nextLive < liveQueue.length
      ) {
        const record = liveQueue[nextLive++];
        activeLive += 1;
        let handle;
        handle = mountKioskLive(record.tile, {
          offscreen:
            deferBroadcast ||
            ["youtube", "tv"].includes(record.tile.dataset.heroMediaKind),
          onStateChange: (state) => {
            if (disposed || finishing) return;
            record.buffering = state === "buffering";
            record.liveReady = state === "live" && record.hasPlayed;
            tick();
          },
          onReady: () => {
            if (disposed || finishing) return;
            handle.reveal();
            record.hasPlayed = true;
            showBoard();
            delete record.camera.scene.dataset.liveRetryAfter;
            record.liveReady = true;
            record.age.textContent = "LIVE";
            record.liveDeadline =
              (heldAt ?? Date.now()) + (duration >= 30000 ? 30000 : 20000);
            scheduleViewing();
          },
          onUnavailable: () => {
            if (disposed || finishing) return;
            record.camera.scene.dataset.liveRetryAfter = String(
              Date.now() + 300000,
            );
            timers.push(
              window.setTimeout(() => {
                if (disposed || finishing) return;
                handle?.dispose();
                record.liveReady = false;
                record.buffering = false;
                record.liveDeadline = 0;
                activeLive -= 1;
                tick();
                startLive();
              }, 0),
            );
          },
        });
        liveHandles.push(handle);
      }
      if (
        shownAt === null &&
        activeLive === 0 &&
        nextLive >= liveQueue.length
      ) {
        finish();
        return;
      }
      scheduleViewing();
    };
    startLive();
  };
  window.addEventListener("pagehide", dispose, { once: true });
  selection.cameras.forEach((camera) => {
    const tile = document.createElement("a");
    tile.className = "rotation-overview-tile";
    tile.dataset.heroName = camera.name;
    tile.dataset.heroMediaKind = camera.scene?.dataset.heroMediaKind || "";
    tile.href = camera.live;
    const media = document.createElement("div");
    media.className = "landing-hero-media rotation-overview-media";
    const image = document.createElement("img");
    image.alt = `${camera.name} latest capture`;
    const label = document.createElement("div");
    label.className = "rotation-overview-label";
    const name = document.createElement("strong");
    name.textContent = camera.name;
    const age = document.createElement("span");
    age.textContent = captureAge(camera.captured);
    label.append(name, age);
    // Keep the ambient view quiet; full descriptions remain in the camera view.
    tile.title = [sourceAge(camera.freshness), camera.caption]
      .filter(Boolean)
      .join(" · ");
    media.append(image);
    tile.append(media, label);
    const record = { tile, image, age, camera, loaded: false };
    records.push(record);
    let settled = false;
    const settle = (loaded) => {
      if (disposed || settled) return;
      settled = true;
      record.loaded = loaded;
      if (loaded) prepareSceneComfort(tile, image);
      completed++;
      finalize();
    };
    image.onload = () => settle(image.naturalWidth > 0);
    image.onerror = () => settle(false);
    timers.push(window.setTimeout(() => settle(false), 8000));
    image.src = captureImageUrl(camera.image, camera.captured);
  });
  return {
    dispose,
    cameras: selection.cameras,
    setHeld: (held) => setHeld(held),
  };
}
