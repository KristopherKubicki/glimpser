const STORAGE = {
  idleEnabled: "comfortIdleEnabled",
  idleSeconds: "comfortIdleSeconds",
  dimOpacity: "comfortDimOpacity",
  dimInMs: "comfortDimInMs",
  brightenMs: "comfortBrightenMs",
  tintEnabled: "comfortTintEnabled",
  tintOpacity: "comfortTintOpacity",
  tintColor: "comfortTintColor",
  tintAutoNight: "comfortTintAutoNight",
  flashGuardEnabled: "flashGuard",
  flashTargetLuma: "flashTargetLuma",
};

const DEFAULTS = {
  idleEnabled: true,
  idleSeconds: 120,
  dimOpacity: 0.6,
  dimInMs: 4500,
  brightenMs: 1800,
  tintEnabled: true,
  tintOpacity: 0.08,
  tintColor: "warm",
  tintAutoNight: true,
  flashGuardEnabled: true,
  flashTargetLuma: 0.55,
};

function clamp(min, v, max) {
  return Math.max(min, Math.min(max, v));
}

function readBool(key, fallback) {
  const v = localStorage.getItem(key);
  if (v == null) return fallback;
  return v !== "0" && v !== "false";
}

function readNum(key, fallback) {
  const v = parseFloat(localStorage.getItem(key) ?? "");
  return Number.isFinite(v) ? v : fallback;
}

function writeBool(key, v) {
  localStorage.setItem(key, v ? "1" : "0");
}

function writeNum(key, v) {
  localStorage.setItem(key, String(v));
}

function readTintColor() {
  const v = (localStorage.getItem(STORAGE.tintColor) || DEFAULTS.tintColor)
    .toString()
    .toLowerCase();
  const allowed = new Set(["warm", "cool", "neutral", "dark"]);
  return allowed.has(v) ? v : DEFAULTS.tintColor;
}

function tintRgba(color, opacity) {
  const a = clamp(0, opacity, 1);
  switch (color) {
    case "cool":
      return `rgba(120, 170, 255, ${a})`;
    case "neutral":
      return `rgba(255, 255, 255, ${a * 0.45})`;
    case "dark":
      return `rgba(0, 0, 0, ${a})`;
    case "warm":
    default:
      return `rgba(255, 160, 40, ${a})`;
  }
}

function prefersReducedMotion() {
  return window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches;
}

let dimmerEl = null;
let tintEl = null;
let idleTimer = null;
let isDimmed = false;
let lastActivityAt = Date.now();

function ensureOverlays() {
  if (!dimmerEl) {
    dimmerEl = document.getElementById("comfort-dimmer");
    if (!dimmerEl) {
      dimmerEl = document.createElement("div");
      dimmerEl.id = "comfort-dimmer";
      document.body.appendChild(dimmerEl);
    }
  }

  if (!tintEl) {
    tintEl = document.getElementById("comfort-tint");
    if (!tintEl) {
      tintEl = document.createElement("div");
      tintEl.id = "comfort-tint";
      document.body.appendChild(tintEl);
    }
  }
}

function setOpacity(el, opacity, durationMs) {
  if (!el) return;
  const ms = Math.max(0, Math.floor(durationMs));

  // If motion is reduced, snap to avoid animated flicker.
  const effectiveMs = prefersReducedMotion() ? 0 : ms;
  el.style.transitionDuration = `${effectiveMs}ms`;
  el.style.opacity = String(clamp(0, opacity, 1));
}

function getTintOpacityNow(baseOpacity, autoNight) {
  if (!autoNight) return baseOpacity;
  const hour = new Date().getHours();
  const isNight = hour >= 20 || hour < 6;
  return isNight ? baseOpacity : 0;
}

function applyComfort() {
  if (!document.body) return;
  ensureOverlays();

  const idleEnabled = readBool(STORAGE.idleEnabled, DEFAULTS.idleEnabled);
  const idleSeconds = clamp(
    10,
    Math.floor(readNum(STORAGE.idleSeconds, DEFAULTS.idleSeconds)),
    60 * 60,
  );
  const dimOpacity = clamp(
    0,
    readNum(STORAGE.dimOpacity, DEFAULTS.dimOpacity),
    1,
  );
  const dimInMs = clamp(0, readNum(STORAGE.dimInMs, DEFAULTS.dimInMs), 30_000);
  const brightenMs = clamp(
    0,
    readNum(STORAGE.brightenMs, DEFAULTS.brightenMs),
    30_000,
  );

  const tintEnabled = readBool(STORAGE.tintEnabled, DEFAULTS.tintEnabled);
  const tintOpacityBase = clamp(
    0,
    readNum(STORAGE.tintOpacity, DEFAULTS.tintOpacity),
    0.6,
  );
  const tintColor = readTintColor();
  const tintAutoNight = readBool(STORAGE.tintAutoNight, DEFAULTS.tintAutoNight);

  // Idle dimmer
  dimmerEl.style.display = idleEnabled ? "block" : "none";
  dimmerEl.dataset.idleSeconds = String(idleSeconds);
  dimmerEl.dataset.dimOpacity = String(dimOpacity);
  dimmerEl.dataset.dimInMs = String(dimInMs);
  dimmerEl.dataset.brightenMs = String(brightenMs);

  // If disabled, ensure we are not dimmed.
  if (!idleEnabled) {
    isDimmed = false;
    setOpacity(dimmerEl, 0, 0);
  }

  // Tint overlay
  tintEl.style.display = tintEnabled ? "block" : "none";
  tintEl.style.backgroundColor = tintRgba(
    tintColor,
    getTintOpacityNow(tintOpacityBase, tintAutoNight),
  );

  // If tint is disabled, clear the overlay.
  if (!tintEnabled) {
    tintEl.style.backgroundColor = "rgba(0,0,0,0)";
  }

  // When settings change, reschedule idle timer.
  scheduleIdle();
}

function dimNow() {
  if (!dimmerEl) return;
  const enabled = readBool(STORAGE.idleEnabled, DEFAULTS.idleEnabled);
  if (!enabled) return;

  const dimOpacity = clamp(
    0,
    readNum(STORAGE.dimOpacity, DEFAULTS.dimOpacity),
    1,
  );
  const dimInMs = clamp(0, readNum(STORAGE.dimInMs, DEFAULTS.dimInMs), 30_000);

  isDimmed = true;
  setOpacity(dimmerEl, dimOpacity, dimInMs);
}

function brightenNow() {
  if (!dimmerEl) return;
  const brightenMs = clamp(
    0,
    readNum(STORAGE.brightenMs, DEFAULTS.brightenMs),
    30_000,
  );

  isDimmed = false;
  setOpacity(dimmerEl, 0, brightenMs);
}

function scheduleIdle() {
  if (idleTimer) {
    clearTimeout(idleTimer);
    idleTimer = null;
  }

  const enabled = readBool(STORAGE.idleEnabled, DEFAULTS.idleEnabled);
  if (!enabled) return;

  const idleSeconds = clamp(
    10,
    Math.floor(readNum(STORAGE.idleSeconds, DEFAULTS.idleSeconds)),
    60 * 60,
  );

  const remainingMs = Math.max(
    0,
    idleSeconds * 1000 - (Date.now() - lastActivityAt),
  );
  idleTimer = setTimeout(() => {
    // Don’t dim when not visible; it just causes a visible fade on tab focus.
    if (document.visibilityState !== "visible") return;
    dimNow();
  }, remainingMs);
}

function markActivity() {
  lastActivityAt = Date.now();
  if (isDimmed) brightenNow();
  scheduleIdle();
}

function wireActivityListeners() {
  const events = [
    "mousemove",
    "mousedown",
    "keydown",
    "touchstart",
    "wheel",
    "scroll",
    "pointerdown",
  ];

  let throttled = false;
  const handler = () => {
    // Throttle to avoid hammering timers on high-frequency events.
    if (throttled) return;
    throttled = true;
    requestAnimationFrame(() => {
      throttled = false;
      markActivity();
    });
  };

  events.forEach((evt) =>
    window.addEventListener(evt, handler, { passive: true }),
  );

  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") {
      // On returning to the tab, treat as activity.
      markActivity();
    }
  });

  window.addEventListener("focus", markActivity);
}

function initComfortSettingsUi() {
  document.addEventListener("DOMContentLoaded", () => {
    const root = document.getElementById("comfort-settings");
    if (!root) return;

    const bindToggle = (id, key, fallback) => {
      const el = document.getElementById(id);
      if (!el) return;
      el.checked = readBool(key, fallback);
      el.addEventListener("change", () => {
        writeBool(key, !!el.checked);
        applyComfort();
      });
    };

    const bindRange = (
      id,
      valueId,
      key,
      fallback,
      { min, max, step, mapIn, mapOut },
    ) => {
      const el = document.getElementById(id);
      const out = valueId ? document.getElementById(valueId) : null;
      if (!el) return;

      const stored = readNum(key, fallback);
      const v = mapIn ? mapIn(stored) : stored;
      el.min = String(min);
      el.max = String(max);
      el.step = String(step);
      el.value = String(clamp(min, v, max));

      const refreshLabel = () => {
        if (!out) return;
        out.textContent = el.dataset.label
          ? el.dataset.label.replace("{v}", el.value)
          : el.value;
      };

      const write = () => {
        const raw = parseFloat(el.value);
        const mapped = mapOut ? mapOut(raw) : raw;
        writeNum(key, mapped);
        refreshLabel();
        applyComfort();
      };

      el.addEventListener("input", () => {
        refreshLabel();
      });
      el.addEventListener("change", write);
      refreshLabel();
    };

    const bindSelect = (id, key, fallback) => {
      const el = document.getElementById(id);
      if (!el) return;
      el.value = (localStorage.getItem(key) || fallback).toString();
      el.addEventListener("change", () => {
        localStorage.setItem(key, el.value);
        applyComfort();
      });
    };

    // Idle dimmer
    bindToggle(
      "comfort-idle-enabled",
      STORAGE.idleEnabled,
      DEFAULTS.idleEnabled,
    );
    bindRange(
      "comfort-idle-seconds",
      "comfort-idle-seconds-val",
      STORAGE.idleSeconds,
      DEFAULTS.idleSeconds,
      {
        min: 10,
        max: 1800,
        step: 10,
      },
    );
    bindRange(
      "comfort-dim-opacity",
      "comfort-dim-opacity-val",
      STORAGE.dimOpacity,
      DEFAULTS.dimOpacity,
      {
        min: 0,
        max: 0.9,
        step: 0.01,
      },
    );
    bindRange(
      "comfort-brighten-ms",
      "comfort-brighten-ms-val",
      STORAGE.brightenMs,
      DEFAULTS.brightenMs,
      {
        min: 0,
        max: 15000,
        step: 100,
      },
    );

    // Tint
    bindToggle(
      "comfort-tint-enabled",
      STORAGE.tintEnabled,
      DEFAULTS.tintEnabled,
    );
    bindToggle(
      "comfort-tint-auto-night",
      STORAGE.tintAutoNight,
      DEFAULTS.tintAutoNight,
    );
    bindSelect("comfort-tint-color", STORAGE.tintColor, DEFAULTS.tintColor);
    bindRange(
      "comfort-tint-opacity",
      "comfort-tint-opacity-val",
      STORAGE.tintOpacity,
      DEFAULTS.tintOpacity,
      {
        min: 0,
        max: 0.4,
        step: 0.01,
      },
    );

    // Flash guard (live view)
    bindToggle(
      "comfort-flash-guard-enabled",
      STORAGE.flashGuardEnabled,
      DEFAULTS.flashGuardEnabled,
    );
    bindRange(
      "comfort-flash-target-luma",
      "comfort-flash-target-luma-val",
      STORAGE.flashTargetLuma,
      DEFAULTS.flashTargetLuma,
      {
        min: 0.2,
        max: 0.8,
        step: 0.01,
      },
    );

    applyComfort();
  });
}

export function initComfort() {
  document.addEventListener("DOMContentLoaded", () => {
    ensureOverlays();
    applyComfort();
    wireActivityListeners();

    // Keep tint "auto-night" dynamic without being jittery.
    setInterval(() => {
      const tintEnabled = readBool(STORAGE.tintEnabled, DEFAULTS.tintEnabled);
      if (!tintEnabled || !tintEl) return;
      const base = clamp(
        0,
        readNum(STORAGE.tintOpacity, DEFAULTS.tintOpacity),
        0.6,
      );
      const color = readTintColor();
      const autoNight = readBool(STORAGE.tintAutoNight, DEFAULTS.tintAutoNight);
      tintEl.style.backgroundColor = tintRgba(
        color,
        getTintOpacityNow(base, autoNight),
      );
    }, 30_000);
  });

  // Expose a tiny API for debugging / future UI entry points.
  window.GlimpserComfort = {
    apply: applyComfort,
    dimNow,
    brightenNow,
    markActivity,
  };

  initComfortSettingsUi();
}
