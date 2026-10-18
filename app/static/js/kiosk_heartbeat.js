// Prefer decoded, non-dropped frames over a media clock that can run frozen.
function playbackPosition(video) {
  try {
    const quality = video.getVideoPlaybackQuality?.();
    if (Number.isFinite(quality?.totalVideoFrames)) {
      const dropped = Number.isFinite(quality.droppedVideoFrames)
        ? quality.droppedVideoFrames
        : 0;
      return {
        kind: "frames",
        value: Math.max(0, quality.totalVideoFrames - dropped),
      };
    }
  } catch {
    // Older browsers retain the best-effort media-clock fallback.
  }
  return { kind: "clock", value: video.currentTime };
}

// Sample rendered media, not playlist membership. These are browser observations,
// not proof of physical display output or camera-scene motion.
export function createPlaybackSampler() {
  const previous = new WeakMap();
  return () => {
    const overview = document.querySelector(
      ".rotation-overview:not(.is-leaving)",
    );
    const scenes = overview
      ? [...overview.querySelectorAll(".rotation-overview-tile")].slice(0, 4)
      : [...document.querySelectorAll(".landing-scene.is-visible")].slice(0, 1);
    return {
      revision:
        document.querySelector("[data-landing-asset-revision]")?.dataset
          .landingAssetRevision || "",
      layout: overview ? "overview" : "single",
      cameras: scenes.map((scene) => {
        const live = scene.dataset.heroName?.startsWith("TV · ")
          ? null
          : scene.querySelector(".kiosk-live-layer.is-playing video");
        const video =
          live ||
          scene.querySelector(".kiosk-timelapse video, .landing-hero-video");
        const image = scene.querySelector(".landing-hero-media > img");
        let state =
          image?.complete && image.naturalWidth > 0 ? "still" : "missing";
        const history = scene.querySelector(".kiosk-timelapse img");
        if (history?.complete && history.naturalWidth > 0)
          state = "history_loaded";
        if (live || (video && !video.paused && video.videoWidth > 0)) {
          const last = previous.get(video);
          const position = playbackPosition(video);
          const advancing =
            !video.paused &&
            video.videoWidth > 0 &&
            last !== undefined &&
            last.kind === position.kind &&
            position.value > last.value;
          previous.set(video, position);
          state = `${live ? "live" : "video"}_${advancing ? "advancing" : "waiting"}`;
        }
        return { name: scene.dataset.heroName || "", state };
      }),
    };
  };
}

// The external kiosk monitor checks these beats, not just server reachability.
export function mountKioskHeartbeat(
  profile,
  { onRestore = () => window.location.reload() } = {},
) {
  if (
    !["office", "living"].includes(profile) ||
    typeof requestAnimationFrame !== "function"
  )
    return () => {};
  let disposed = false,
    suspended = false,
    restoreRequested = false,
    pending = null,
    frame = null,
    timer = null;
  const samplePlayback = createPlaybackSampler();
  const beat = () => {
    if (disposed || suspended || pending || frame !== null || document.hidden)
      return;
    frame = requestAnimationFrame(() => {
      frame = null;
      if (disposed || suspended) return;
      const request = {
        controller:
          typeof AbortController === "function" ? new AbortController() : null,
        timeout: null,
      };
      pending = request;
      request.timeout = setTimeout(() => {
        request.controller?.abort();
        // Some embedded browsers leave an aborted fetch unsettled. Let the
        // next interval retry instead of silencing this kiosk indefinitely.
        if (pending === request) pending = null;
      }, 5000);
      void fetch(`/kiosk_health?profile=${profile}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(samplePlayback()),
        cache: "no-store",
        signal: request.controller?.signal,
      })
        .catch(() => {})
        .finally(() => {
          clearTimeout(request.timeout);
          // A pre-navigation request must not clear the restored page's request.
          if (pending === request) pending = null;
        });
    });
  };
  const suspend = () => {
    suspended = true;
    clearInterval(timer);
    timer = null;
    if (frame !== null) cancelAnimationFrame(frame);
    frame = null;
    if (pending) {
      clearTimeout(pending.timeout);
      pending.controller?.abort();
      pending = null;
    }
  };
  const start = () => {
    if (disposed || timer !== null) return;
    suspended = false;
    beat();
    timer = setInterval(beat, 15000);
  };
  const restore = (event) => {
    // Rotation and media also dispose on pagehide. Reload the whole view rather
    // than reporting healthy heartbeats for a restored but inert scene.
    if (!event.persisted || disposed || restoreRequested) return;
    restoreRequested = true;
    onRestore();
  };
  const dispose = () => {
    disposed = true;
    suspend();
    window.removeEventListener("pagehide", suspend);
    window.removeEventListener("pageshow", restore);
  };
  start();
  window.addEventListener("pagehide", suspend);
  window.addEventListener("pageshow", restore);
  return dispose;
}
