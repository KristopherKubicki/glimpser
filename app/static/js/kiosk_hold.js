import { captureAge, sourceAge } from "./capture_age.js";

// One bounded saved frame per room; never label a saved image as live. This also
// works on LAN HTTP kiosks where service workers are unavailable.
export function createKioskHold(stage, profile) {
  const key = `glimpser.saved-view.v1.${profile || "default"}`;
  let saved = null;
  let active = false;
  let node = null;
  let lastSource = "";
  let reason = "";
  try {
    const value = JSON.parse(localStorage.getItem(key) || "null");
    if (
      value?.image?.startsWith("data:image/jpeg;base64,") &&
      value.image.length < 1500000 &&
      typeof value.name === "string" &&
      typeof value.captured === "string"
    )
      saved = value;
  } catch {
    /* Storage is optional. */
  }

  const paint = () => {
    if (!active || !node) return;
    const label = node.querySelector("strong");
    const state =
      navigator.onLine === false ? "KIOSK OFFLINE" : "FEED INTERRUPTED";
    label.textContent = saved ? `${state} · Saved view: ${saved.name}` : state;
    node.querySelector("p").textContent = saved
      ? `Captured ${captureAge(saved.captured)} · ${sourceAge(saved.freshness)} · ${reason}`
      : `No saved image available · ${reason}`;
  };
  return {
    get active() {
      return active;
    },
    remember(image, scene) {
      if (!image?.naturalWidth || !image.naturalHeight) return;
      const source = image.currentSrc || image.src;
      if (!source || source === lastSource) return;
      try {
        const canvas = document.createElement("canvas");
        const scale = Math.min(
          1,
          1920 / image.naturalWidth,
          1080 / image.naturalHeight,
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
        lastSource = source;
        // A status timeout can precede the first successful image load. Keep
        // that accepted frame visible without falsely declaring recovery.
        if (active && node) {
          let heldImage = node.querySelector("img");
          if (!heldImage) {
            heldImage = document.createElement("img");
            node.prepend(heldImage);
          }
          heldImage.src = saved.image;
          heldImage.alt = `Saved view of ${saved.name}`;
          paint();
        }
        try {
          localStorage.setItem(key, JSON.stringify(saved));
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
        if (saved) {
          const image = document.createElement("img");
          image.src = saved.image;
          image.alt = `Saved view of ${saved.name}`;
          node.append(image);
        }
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
    },
    update: paint,
    recover() {
      active = false;
      delete stage.dataset.kioskOffline;
      node?.remove();
      node = null;
    },
    dispose() {
      node?.remove();
    },
  };
}
