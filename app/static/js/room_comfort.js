// Room light and scene brightness are separate signals. Never infer the room's
// lighting from whichever camera happens to be on screen.
export function roomLightLevel(lux, previous = "dim") {
  if (!Number.isFinite(lux) || lux < 0) return previous;
  if (previous === "dark" && lux < 25) return "dark";
  if (previous === "bright" && lux > 45) return "bright";
  return lux < 15 ? "dark" : lux > 70 ? "bright" : "dim";
}

export function scheduledRoomLight(hour = new Date().getHours()) {
  return hour >= 21 || hour < 6
    ? "dark"
    : hour >= 19 || hour < 8
      ? "dim"
      : "bright";
}

export function prepareSceneComfort(
  scene,
  image = scene.querySelector(".landing-hero-media img"),
) {
  // Unknown/loading frames start capped, so a white page cannot appear at full
  // brightness while its pixels are still unavailable.
  let bright = true;
  if (image?.complete && image.naturalWidth) {
    try {
      const canvas = document.createElement("canvas");
      canvas.width = 24;
      canvas.height = 16;
      const ctx = canvas.getContext("2d", { willReadFrequently: true });
      ctx.drawImage(image, 0, 0, 24, 16);
      const { data } = ctx.getImageData(0, 0, 24, 16);
      let sum = 0,
        highlights = 0;
      for (let i = 0; i < data.length; i += 4) {
        const light =
          (0.2126 * data[i] + 0.7152 * data[i + 1] + 0.0722 * data[i + 2]) /
          255;
        sum += light;
        if (light > 0.85) highlights++;
      }
      bright =
        sum / (data.length / 4) > 0.45 || highlights / (data.length / 4) > 0.18;
    } catch {
      // Cross-origin and unsupported canvas retain the safe incoming cap.
    }
  }
  const clamp = bright && !scene.classList.contains("scene-bright");
  if (clamp) scene.classList.add("scene-clamping");
  scene.classList.toggle("scene-bright", bright);
  if (clamp) {
    // Commit the safety cap without animating through the previous brightness.
    // Remove only the override so later room-light changes still fade smoothly.
    void scene.offsetWidth;
    scene.classList.remove("scene-clamping");
  }
}

export function mountRoomComfort(stage) {
  if (!document.querySelector("link[data-room-comfort]")) {
    const link = document.createElement("link");
    link.rel = "stylesheet";
    link.href = "/static/css/room_comfort.css?v=20261009-night-clamp";
    link.dataset.roomComfort = "";
    document.head.append(link);
  }
  let level = scheduledRoomLight();
  let sensor = null;
  let sampledAt = 0;
  let smoothedLux = null;
  let disposed = false;
  const apply = (next, source) => {
    level = next;
    for (const value of ["dark", "dim", "bright"])
      stage.classList.toggle(`room-${value}`, value === next);
    stage.dataset.roomLightSource = source;
  };
  const fallback = () => {
    if (!sampledAt || Date.now() - sampledAt > 60000) {
      // A recovered sensor starts from its new reading, not an old dark-room average.
      smoothedLux = null;
      apply(scheduledRoomLight(), "schedule");
    }
  };
  apply(level, "schedule");
  // Feature detection matters: most wall browsers do not expose a light sensor.
  // Never prompt for camera access or pretend a time fallback is a lux reading.
  if (typeof window.AmbientLightSensor === "function") {
    try {
      sensor = new window.AmbientLightSensor({ frequency: 1 });
      sensor.addEventListener("reading", () => {
        if (disposed) return;
        const lux = sensor.illuminance;
        if (!Number.isFinite(lux) || lux < 0) return;
        smoothedLux =
          smoothedLux === null ? lux : 0.2 * lux + 0.8 * smoothedLux;
        sampledAt = Date.now();
        apply(roomLightLevel(smoothedLux, level), "sensor");
      });
      sensor.addEventListener("error", () => {
        if (disposed) return;
        sampledAt = 0;
        fallback();
      });
      sensor.start();
    } catch {
      sensor?.stop?.();
      sensor = null;
    }
  }
  const onLoad = (event) => {
    const scene = event.target.closest?.(".landing-scene");
    if (scene) prepareSceneComfort(scene);
  };
  stage.addEventListener("load", onLoad, true);
  const timer = setInterval(fallback, 15000);
  const dispose = () => {
    if (disposed) return;
    disposed = true;
    clearInterval(timer);
    sensor?.stop();
    stage.removeEventListener("load", onLoad, true);
    window.removeEventListener("pagehide", dispose);
  };
  window.addEventListener("pagehide", dispose, { once: true });
  return dispose;
}
