// User-driven comparisons only; never start or download every review video.
export function initEnhancementReview(root = document) {
  initStillComparisons(root);
  const sessions = [];
  for (const article of root.querySelectorAll("[data-enhancement-review]")) {
    const pair = [...article.querySelectorAll("video")];
    if (pair.length !== 2) continue;
    const button = article.querySelector("[data-compare-play]");
    const status = article.querySelector("[data-compare-status]");
    let generation = 0;
    let cancelStart = null;
    const stop = () => {
      generation++;
      cancelStart?.();
      cancelStart = null;
      pair.forEach((video) => video.pause());
      status.textContent = "Comparison paused. Play together to resume.";
    };
    sessions.push(stop);
    button.hidden = false;
    button.addEventListener("click", async () => {
      if (pair.some((video) => !video.paused)) {
        stop();
        status.textContent =
          "Comparison paused. Click again to resume together.";
        return;
      }
      stop();
      sessions.filter((other) => other !== stop).forEach((other) => other());
      const request = generation;
      const start = Number.isFinite(pair[0].currentTime)
        ? pair[0].currentTime
        : 0;
      pair.forEach((video) => {
        video.muted = true;
        video.playbackRate = 1;
        video.currentTime = start;
      });
      status.textContent = "Starting comparison…";
      let startupTimer;
      const deadline = new Promise((_, reject) => {
        startupTimer = window.setTimeout(
          () => reject(new Error("Playback start timed out")),
          8000,
        );
        cancelStart = () => {
          window.clearTimeout(startupTimer);
          reject(new Error("Comparison superseded"));
        };
      });
      // Some older media implementations throw before Promise.race is attached.
      deadline.catch(() => {});
      try {
        await Promise.race([
          Promise.all(pair.map((video) => video.play())),
          deadline,
        ]);
        if (request !== generation) return;
        status.textContent =
          "Playing both versions · pause either to stop both";
      } catch {
        if (request !== generation) return;
        stop();
        status.textContent =
          "Comparison could not start. Use the individual controls.";
      } finally {
        window.clearTimeout(startupTimer);
        if (request === generation) cancelStart = null;
      }
    });
    pair.forEach((video) => {
      video.addEventListener("pause", () => {
        if (pair.some((item) => !item.paused)) stop();
      });
      video.addEventListener("ended", stop);
      video.addEventListener("error", stop);
      // Hold the comparison together rather than compare different moments
      // when one stream buffers. Restart is explicitly user-driven.
      video.addEventListener("waiting", () => {
        if (pair.every((item) => item.paused)) return;
        stop();
        status.textContent =
          "Comparison paused while loading. Play together to resume.";
      });
    });
  }
}

if (typeof document !== "undefined") initEnhancementReview();

export function initStillComparisons(root = document) {
  for (const card of root.querySelectorAll("[data-still-compare]")) {
    if (card.dataset.initialized) continue;
    const height = Number(card.dataset.height);
    if (!Number.isFinite(height) || height <= 0) continue;
    card.dataset.initialized = "true";
    const svg = card.querySelector("[data-comparison-image]");
    const range = card.querySelector("[data-reveal-range]");
    const zoom = card.querySelector("[data-detail-zoom]");
    const reveal = card.querySelector("[data-reveal]");
    const divider = card.querySelector("[data-divider]");
    const status = card.querySelector("[data-still-status]");
    const render = () => {
      const fraction = Math.max(0, Math.min(100, Number(range.value))) / 100;
      const width = zoom.checked ? 550 : 1100;
      const h = zoom.checked ? height / 2 : height;
      const x = (1100 - width) / 2;
      const y = (height - h) / 2;
      const split = x + width * fraction;
      svg.setAttribute("viewBox", `${x} ${y} ${width} ${h}`);
      for (const [key, value] of Object.entries({
        x: split,
        y,
        width: width * (1 - fraction),
        height: h,
      })) {
        reveal.setAttribute(key, String(value));
      }
      divider.setAttribute("x1", String(split));
      divider.setAttribute("x2", String(split));
      divider.setAttribute("y1", String(y));
      divider.setAttribute("y2", String(y + h));
      divider.setAttribute(
        "visibility",
        fraction === 0 || fraction === 1 ? "hidden" : "visible",
      );
      const label =
        fraction === 1
          ? "Original only"
          : fraction === 0
            ? "Processed only"
            : "Original left · processed right";
      status.textContent = `${label} · ${zoom.checked ? "2× center detail" : "full frame"}`;
      range.setAttribute("aria-valuetext", label);
    };
    range.addEventListener("input", render);
    zoom.addEventListener("change", render);
    for (const [selector, value] of [
      ["[data-original]", 100],
      ["[data-processed]", 0],
      ["[data-split]", 50],
    ]) {
      card.querySelector(selector).addEventListener("click", () => {
        range.value = String(value);
        render();
      });
    }
    for (const image of svg.querySelectorAll("image")) {
      image.addEventListener("error", () => {
        svg.setAttribute("visibility", "hidden");
        card.querySelector("[data-still-controls]").hidden = true;
        status.textContent =
          "Comparison unavailable. Use the full-size links below; originals are retained.";
      });
    }
    card.querySelector("[data-still-controls]").hidden = false;
    render();
  }
}
