import { captureAge, sourceAge } from "./capture_age.js";

// A bounded saved playlist per room; never label cached images as live. This also
// works on LAN HTTP kiosks where service workers are unavailable.
export function createKioskHold(stage, profile) {
  const key = `glimpser.saved-view.v1.${profile || "default"}`;
  const playlistKey = `glimpser.saved-playlist.v1.${profile || "default"}`;
  const maxFrames = 8;
  const maxCharacters = 3000000;
  let frames = [];
  let index = 0;
  let rotationTimer = null;
  let saved = null;
  let active = false;
  let node = null;
  const lastSources = new Map();
  let reason = "";
  const valid = (value) =>
    value?.image?.startsWith("data:image/jpeg;base64,") &&
    value.image.length < 1500000 &&
    typeof value.name === "string" &&
    typeof value.captured === "string";
  const bound = () => {
    while (
      frames.length > maxFrames ||
      JSON.stringify(frames).length > maxCharacters
    )
      frames.shift();
  };
  try {
    const stored = JSON.parse(localStorage.getItem(playlistKey) || "null");
    if (Array.isArray(stored)) frames = stored.filter(valid);
    if (!frames.length) {
      const legacy = JSON.parse(localStorage.getItem(key) || "null");
      if (valid(legacy)) frames = [legacy];
    }
    bound();
    index = Math.max(0, frames.length - 1);
    saved = frames[index] || null;
  } catch {
    /* Storage is optional; rotation can still use in-memory images. */
  }

  const paint = () => {
    if (!active || !node) return;
    const label = node.querySelector("strong");
    const state = navigator.onLine === false ? "Offline" : "Reconnecting";
    label.textContent = saved ? `Saved view: ${saved.name}` : state;
    if (saved) {
      let image = node.querySelector("img");
      if (!image) {
        image = document.createElement("img");
        node.prepend(image);
      }
      if (image.getAttribute("src") !== saved.image) image.src = saved.image;
      image.alt = `Saved view of ${saved.name}`;
    }
    const caption = node.querySelector("p");
    if (saved) {
      const freshness = saved.freshness || {};
      const sourceTime = freshness.published_at || freshness.inherited_at;
      caption.textContent = [
        `Captured ${captureAge(saved.captured)}`,
        sourceTime ? `Source ${captureAge(sourceTime)}` : "Source time unknown",
        state,
      ].join(" · ");
      // Keep troubleshooting details available without filling the TV caption.
      caption.title = [reason, sourceAge(freshness)]
        .filter(Boolean)
        .join(" · ");
    } else {
      caption.textContent = "Waiting for a saved camera view";
      caption.title = reason;
    }
  };
  return {
    get active() {
      return active;
    },
    get available() {
      return frames.length > 0;
    },
    remember(image, scene) {
      if (!image?.naturalWidth || !image.naturalHeight) return;
      const source = image.currentSrc || image.src;
      const name = scene.dataset.heroName || "Camera";
      if (!source || source === lastSources.get(name)) return;
      try {
        const canvas = document.createElement("canvas");
        const scale = Math.min(
          1,
          1280 / image.naturalWidth,
          720 / image.naturalHeight,
        );
        canvas.width = Math.round(image.naturalWidth * scale);
        canvas.height = Math.round(image.naturalHeight * scale);
        const context = canvas.getContext("2d");
        if (!context) return;
        context.drawImage(image, 0, 0, canvas.width, canvas.height);
        const data = canvas.toDataURL("image/jpeg", 0.72);
        if (
          !data.startsWith("data:image/jpeg;base64,") ||
          data.length >= 1500000
        )
          return;
        saved = {
          image: data,
          name: scene.dataset.heroName || "Camera",
          captured:
            scene.querySelector("[data-capture-age]")?.dataset.captureAge ||
            image.dataset.expectedCaptureTime ||
            "",
          freshness: JSON.parse(
            scene.querySelector("[data-source-freshness]")?.dataset
              .sourceFreshness || "{}",
          ),
        };
        lastSources.set(name, source);
        frames = frames.filter((frame) => frame.name !== name);
        frames.push(saved);
        bound();
        index = Math.max(0, frames.length - 1);
        for (const camera of lastSources.keys()) {
          if (!frames.some((frame) => frame.name === camera))
            lastSources.delete(camera);
        }
        // A status timeout can precede the first successful image load. Keep
        // that accepted frame visible without falsely declaring recovery.
        if (active && node) paint();

        try {
          localStorage.setItem(playlistKey, JSON.stringify(frames));
          localStorage.removeItem(key);
        } catch {
          /* Keep the in-memory frame. */
        }
      } catch {
        /* A canvas/storage restriction must not break the kiosk. */
      }
    },
    hold(message) {
      reason = message;
      active = true;
      stage.dataset.kioskOffline = "true";
      if (!node) {
        node = document.createElement("section");
        node.className = "kiosk-offline-view";
        const caption = document.createElement("div");
        caption.className = "kiosk-offline-caption";
        caption.setAttribute("role", "status");
        caption.append(
          document.createElement("strong"),
          document.createElement("p"),
        );
        node.append(caption);
        stage.append(node);
      }
      paint();
      if (rotationTimer === null) {
        rotationTimer = window.setInterval(() => {
          if (document.hidden || !active || frames.length < 2) return;
          index = (index + 1) % frames.length;
          saved = frames[index];
          paint();
        }, 15000);
      }
    },
    update: paint,
    recover() {
      active = false;
      window.clearInterval(rotationTimer);
      rotationTimer = null;
      delete stage.dataset.kioskOffline;
      node?.remove();
      node = null;
    },
    dispose() {
      active = false;
      window.clearInterval(rotationTimer);
      rotationTimer = null;
      delete stage.dataset.kioskOffline;
      node?.remove();
      node = null;
    },
  };
}
