import { presentationValue } from "./presentation_config.js";
import { captureAge } from "./capture_age.js";
import { HOUSE_EXTERIOR_CAMERAS } from "./kiosk_live.js?v=20261017-media-lifecycle";

export const TIMELAPSE_INTERVAL_MS = 30000;
export const TIMELAPSE_PRELOAD_LEAD_MS = 25000;
const CAMERA_GROUPS = new Set([
  presentationValue("storeone"),
  "beach",
  "beachhouse",
  "chicago",
  "garden",
  presentationValue("storetwo"),
  "kenosha",
  presentationValue("home"),
  "lincolnwood",
  "marine",
  "milwaukee",
  "northpoint",
  "plants",
  "skyline",
  "traffic",
  "waukegan",
]);

// Physical landscape views only: lake maps and weather charts do not count.
// Explicit names include sky cameras whose broad Weather group is not a camera
// group. Freshness checks below still gate every scenic opportunity.
export const SCENIC_CAMERAS = new Set([
  "Hancock",
  "CindysRooftopBean",
  "InstacamChicago",
  "Shedd",
  "Northwestern",
  "DeerfieldCarusoWeatherbug",
  "WaukeganHarborWeatherbug",
  "ZionPublicSchoolWeatherbug",
  "AntiochGrassLakeWeatherbug",
  "ElginCityWeatherbug",
  "StCharlesWeatherbug",
  "WoodstockSquareWeatherbug",
  "WGNTVSkycam",
  "CollegeOfDuPage",
  "SheboyganBeach",
  "SouthHavenSouthBeachGLERL",
  "MichiganCityPierGLERL",
  "MuskegonChannelGLERL",

  "Elmhurst",
  "WaukeganBuoy",
  "BeachSouthJetty",
  "BeachShore",
  "BeachBioswale",
  "BeachGravel",
  "BeachMapleTree",
  "Beach_Google_Backyard",
  "Beach_Google_Front_Yard",
  "CarthageCollegeKenosha",
  "ChicagoPlaypenLakefrontLive",
  "SkylineChicagoFrontlakeTrail",
  "LincolnPark2800LakeShore",
]);

export function scenicEligible(scene, profile) {
  if (!["office", "living"].includes(profile)) return false;
  if (!SCENIC_CAMERAS.has(scene?.dataset.heroName)) return false;
  if (scene.dataset.landingFeedUnavailable === "true") return false;
  try {
    const freshness = JSON.parse(
      scene.querySelector("[data-source-freshness]")?.dataset.sourceFreshness ||
        "{}",
    );
    return ![
      "capture_overdue",
      "retained",
      "source_unchanged",
      "unchanged_since",
      "older",
      "clock_ahead",
      "waiting_for_browser",
    ].some((key) => freshness[key]);
  } catch {
    return false;
  }
}

export function timelapseEligible(scene, profile) {
  if (!scene?.dataset.heroName || !["office", "living"].includes(profile))
    return false;
  if (scene.dataset.landingFeedUnavailable === "true") return false;
  if (scene.dataset.heroReplayAvailable === "true") return true;
  if (scenicEligible(scene, profile)) return true;
  if (HOUSE_EXTERIOR_CAMERAS.has(scene.dataset.heroName)) return true;
  const group = scene
    .querySelector("[data-area-label]")
    ?.dataset.areaLabel?.toLowerCase();
  return CAMERA_GROUPS.has(group);
}

// Keep both initial playback and later opportunities independent of page uptime.
export function timelapseIsDue(lastPlayedAt, now = Date.now()) {
  return lastPlayedAt === null || now - lastPlayedAt >= TIMELAPSE_INTERVAL_MS;
}

let prepared = null;
const lastReplay = new Set();

export function preferCurrentView(
  historyDue,
  lastHistoryAttempt,
  lastLive,
  priority,
) {
  if (priority || !historyDue) return true;
  return (
    lastHistoryAttempt !== null &&
    (lastLive === null || lastHistoryAttempt > lastLive)
  );
}

export function createHistoryMemory() {
  const shown = new Map();
  return {
    repeats(camera, start, end, now = Date.now()) {
      const prior = shown.get(camera);
      // Small additions to the same history do not make a useful new review.
      return Boolean(
        prior &&
          now - prior.at < 10 * 60 * 1000 &&
          Math.abs(start - prior.start) < 300 &&
          Math.abs(end - prior.end) < 300,
      );
    },
    remember(camera, start, end, now = Date.now()) {
      shown.delete(camera);
      shown.set(camera, { start, end, at: now });
      if (shown.size > 128) shown.delete(shown.keys().next().value);
    },
  };
}
const historyMemory = createHistoryMemory();

export function cancelTimelapsePreload() {
  const prior = prepared;
  prepared = null;
  prior?.cancel();
}

// Only one upcoming clip is fetched; failed preloads never affect rotation.
export function preloadTimelapse(camera) {
  if (!camera || typeof AbortController !== "function") return;
  if (prepared?.camera === camera && prepared.expires > Date.now()) return;
  cancelTimelapsePreload();
  const controller = new AbortController();
  let finishCancellation;
  const cancelled = new Promise((resolve) => {
    finishCancellation = resolve;
  });
  const cancel = () => {
    window.clearTimeout(timeout);
    controller.abort();
    // Aborting a fetch is best effort; always release its future consumer.
    finishCancellation(null);
  };
  // Preparing a cold clip can take longer than the on-screen wait budget.
  const timeout = window.setTimeout(cancel, 25000);
  prepared = {
    camera,
    cancel,
    // A live startup plus its viewing window can exceed a minute.
    // Keep this single clip through that handoff; playback still checks age.
    expires: Date.now() + 120000,
    response: Promise.race([
      cancelled,
      Promise.resolve()
        .then(() =>
          controller.signal.aborted
            ? null
            : fetch(`/timelapse/${encodeURIComponent(camera)}.gif`, {
                cache: "no-store",
                signal: controller.signal,
              }),
        )
        .then(async (response) => {
          if (!response?.ok) return null;
          const blob = await response.blob();
          return {
            ok: true,
            headers: response.headers,
            blob: async () => blob,
          };
        })
        .catch(() => null),
    ]).finally(() => window.clearTimeout(timeout)),
  };
}

// A missing timelapse never advances rotation or changes the accepted still.
export function mountTimelapse(
  camera,
  scene,
  { onReady = () => {}, onUnavailable = () => {}, onEnded = () => {} } = {},
) {
  const host = scene.querySelector(".landing-hero-media");
  let disposed = false,
    objectUrl = null,
    lifetime = null,
    ageTimer = null,
    fadeTimer = null,
    claimedPreload = null,
    cancelAttempt = null,
    decodeTimer = null,
    decodeToken = null;
  const node = document.createElement("div");
  node.className = "kiosk-timelapse";
  let image = document.createElement("img");
  image.alt = `${camera} recorded timelapse`;
  const label = document.createElement("div");
  label.className = "kiosk-timelapse-label";
  const title = document.createElement("strong");
  title.textContent = `${camera} · RECORDED HISTORY`;
  const detail = document.createElement("span");
  const playback = document.createElement("span");
  const progress = document.createElement("progress");
  progress.setAttribute("aria-label", "Recorded clip playback");
  progress.max = 1;
  progress.value = 0;
  const next = document.createTextNode("");
  playback.append(progress, next);
  label.append(title, detail, playback);
  node.append(image, label);
  const dispose = () => {
    if (disposed) return;
    disposed = true;
    decodeToken = null;
    window.removeEventListener("pagehide", dispose);
    cancelAttempt?.();
    claimedPreload?.cancel();
    claimedPreload = null;
    window.clearTimeout(timeout);
    window.clearTimeout(decodeTimer);
    window.clearTimeout(lifetime);
    window.clearTimeout(fadeTimer);
    window.clearInterval(ageTimer);
    image.onload = null;
    image.onerror = null;
    image.removeAttribute("src");
    node.remove();
    scene.classList.remove("has-timelapse");
    if (objectUrl) URL.revokeObjectURL(objectUrl);
  };
  const fail = () => {
    if (disposed) return;
    dispose();
    onUnavailable();
  };
  const loadDeadline = performance.now() + 8000;
  const timeout = window.setTimeout(fail, 8000);
  window.addEventListener("pagehide", dispose);
  if (!host) {
    fail();
    return { dispose };
  }
  // Alternate available buffered cameras between recent action and long history.
  // One shared deadline bounds both attempts; no failure advances the rotation.
  const preferReplay =
    scene.dataset.heroReplayAvailable === "true" && !lastReplay.has(camera);
  const takeTimelapse = (signal) => {
    if (prepared?.camera === camera) {
      const candidate = prepared;
      prepared = null;
      if (candidate.expires > Date.now()) {
        // Ownership moves to this scene, including its pending download.
        claimedPreload = candidate;
        return candidate.response;
      }
      candidate.cancel();
    }
    return fetch(`/timelapse/${encodeURIComponent(camera)}.gif`, {
      cache: "no-store",
      signal,
    });
  };
  // A camera without long history must get another replay opportunity next time.
  if (!preferReplay) lastReplay.delete(camera);
  const loadReplay = async (signal) => {
    if (scene.dataset.heroReplayAvailable === "true") {
      let response = null;
      try {
        response = await fetch(
          `/event_buffer/${encodeURIComponent(camera)}.gif?recent=1`,
          { cache: "no-store", signal },
        );
      } catch {
        // Replay is optional. Try saved history within the same deadline;
        // disposal below still prevents late requests after a hold/scene exit.
      }
      if (disposed) return null;
      if (response?.ok) {
        const start = Number(response.headers.get("X-Replay-Start"));
        const end = Number(response.headers.get("X-Replay-End"));
        const frames = Number(response.headers.get("X-Replay-Frames"));
        const fps = Number(response.headers.get("X-Replay-Fps"));
        const encodedDuration = response.headers.get("X-Replay-Duration");
        // Old servers have no duration header; retain their bounded estimate.
        const duration =
          encodedDuration == null
            ? Math.min(12, ((end - start) * frames) / (frames - 1))
            : Number(encodedDuration);
        if (
          [start, end, frames, fps, duration].every(Number.isFinite) &&
          start > 0 &&
          end > start &&
          end - start <= 30 &&
          Date.now() / 1000 - end <= 30 &&
          end <= Date.now() / 1000 + 5 &&
          Number.isInteger(frames) &&
          frames >= 2 &&
          frames <= 30 &&
          fps > 0 &&
          fps <= 30 &&
          duration > 0 &&
          duration <= 60
        ) {
          return {
            response,
            start,
            end,
            fps,
            replay: true,
            duration,
          };
        }
      }
    }
    return null;
  };
  const loadHistory = async (signal) => {
    if (disposed) return null;
    const response = await takeTimelapse(signal);
    if (!response?.ok) return null;
    const start = Number(response.headers.get("X-Timelapse-Start"));
    const end = Number(response.headers.get("X-Timelapse-End"));
    const frames = Number(response.headers.get("X-Timelapse-Frames"));
    const duration = Number(response.headers.get("X-Timelapse-Duration"));
    if (
      ![start, end, frames, duration].every(Number.isFinite) ||
      end - start < 600 ||
      end - start > 86400 ||
      Date.now() / 1000 - end > 5400 ||
      end > Date.now() / 1000 + 5 ||
      !Number.isInteger(frames) ||
      frames < 6 ||
      frames > 24 ||
      duration <= 0 ||
      duration > 25
    )
      return null;
    if (historyMemory.repeats(camera, start, end)) return null;
    return { response, start, end, duration, replay: false };
  };
  const download = async (attempt, budget) => {
    const controller =
      typeof AbortController === "function" ? new AbortController() : null;
    let active = true,
      finishCancellation;
    const cancelled = new Promise((resolve) => {
      finishCancellation = resolve;
    });
    const stop = () => {
      active = false;
      window.clearTimeout(deadline);
      controller?.abort();
      if (attempt === loadHistory) claimedPreload?.cancel();
      finishCancellation(null);
    };
    const decodeDeadline = performance.now() + budget;
    const deadline = window.setTimeout(stop, budget);
    cancelAttempt = stop;
    try {
      return await Promise.race([
        cancelled,
        (async () => {
          const clip = await attempt(controller?.signal);
          if (!clip || !active || disposed) return null;
          const blob = await clip.response.blob();
          return active && !disposed ? { ...clip, blob, decodeDeadline } : null;
        })(),
      ]);
    } finally {
      stop();
      if (cancelAttempt === stop) cancelAttempt = null;
    }
  };
  const attempts = preferReplay
    ? [loadReplay, loadHistory]
    : [loadHistory, loadReplay];
  let nextAttempt = 0;
  const load = async () => {
    // Try the other recorded format when the preferred one is unavailable.
    // Reserve half the total deadline for the alternate when both are offered.
    // Downloads and decoding share that budget. A corrupt image can therefore
    // yield to the remaining format without restarting either request.
    while (nextAttempt < attempts.length) {
      if (disposed) return null;
      const index = nextAttempt++;
      const attempt = attempts[index];
      try {
        const clip = await download(
          attempt,
          index === 0 && scene.dataset.heroReplayAvailable === "true"
            ? 4000
            : Math.max(0, loadDeadline - performance.now()),
        );
        if (clip) return clip;
      } catch {
        // A missing history must not hide an available fresh replay.
      }
    }
    return null;
  };
  const showNext = () =>
    load()
      .then((clip) => {
        if (!clip || disposed) {
          fail();
          return;
        }
        const { blob, start, end, duration, replay, fps, decodeDeadline } =
          clip;
        // A separate element per decode keeps events from an abandoned image
        // from being delivered to the replacement's listeners.
        const replacement = document.createElement("img");
        replacement.alt = `${camera} recorded timelapse`;
        image.replaceWith(replacement);
        image = replacement;
        objectUrl = URL.createObjectURL(blob);
        const token = {};
        decodeToken = token;
        const retry = () => {
          if (disposed || decodeToken !== token) return;
          decodeToken = null;
          window.clearTimeout(decodeTimer);
          image.onload = null;
          image.onerror = null;
          image.removeAttribute("src");
          URL.revokeObjectURL(objectUrl);
          objectUrl = null;
          showNext();
        };
        image.onload = () => {
          if (disposed || decodeToken !== token) return;
          if (document.hidden) {
            fail();
            return;
          }
          decodeToken = null;
          window.clearTimeout(decodeTimer);
          image.onload = null;
          image.onerror = fail;
          window.clearTimeout(timeout);
          if (replay) {
            lastReplay.add(camera);
            title.textContent = `${camera} · RECENT REPLAY`;
            image.alt = `${camera} recorded short replay`;
          } else {
            lastReplay.delete(camera);
          }
          const startedAt = performance.now();
          const tick = () => {
            const elapsed = Math.max(0, (performance.now() - startedAt) / 1000);
            progress.value = Math.min(1, elapsed / duration);
            next.textContent = ` · ${Math.max(0, Math.ceil(duration - elapsed))}s left · Next: latest capture`;
            detail.textContent = replay
              ? `${Math.round(duration)}s preview · from ${captureAge(new Date(start * 1000).toISOString())} · ${fps} fps measured · recorded, not live`
              : historyLabel(start, end);
          };
          tick();
          host.append(node);
          scene.classList.add("has-timelapse");
          // Read the actual CSS fade so the scene survives the entire transition.
          // Reduced-motion styles have no transition and therefore no extra hold.
          const fadeMs = Math.max(
            0,
            ...window
              .getComputedStyle(node)
              .transitionDuration.split(",")
              .map((value) => {
                const seconds = Number.parseFloat(value);
                return Number.isFinite(seconds)
                  ? seconds * (value.trim().endsWith("ms") ? 1 : 1000)
                  : 0;
              }),
          );
          onReady(duration + fadeMs / 1000);
          if (disposed) return;
          ageTimer = window.setInterval(tick, 1000);
          fadeTimer = window.setTimeout(() => {
            // Loading is not watching: interrupted history remains eligible.
            if (!replay && !document.hidden)
              historyMemory.remember(camera, start, end);
            node.classList.add("is-ending");
          }, duration * 1000);
          lifetime = window.setTimeout(
            () => {
              dispose();
              onEnded();
            },
            duration * 1000 + fadeMs,
          );
        };
        image.onerror = retry;
        decodeTimer = window.setTimeout(
          retry,
          Math.max(0, decodeDeadline - performance.now()),
        );
        image.src = objectUrl;
      })
      .catch(fail);
  showNext();
  return { dispose };
}

export function historyLabel(start, end) {
  const minutes = Math.round((end - start) / 60);
  const span =
    minutes >= 120 ? `${(minutes / 60).toFixed(1)} HOURS` : `${minutes} MIN`;
  const format = (stamp) =>
    new Date(stamp * 1000).toLocaleString([], {
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
    });
  return `${span} OF HISTORY · ${format(start)} – ${format(end)} · sampled, recorded${end - start < 23 * 3600 ? " · shorter available history" : ""}`;
}
