import { jest } from "@jest/globals";
import { readFileSync } from "node:fs";
import {
  hasUsableImageFrame,
  timelapseSceneDwellMs,
  canInterruptScene,
} from "../../app/static/js/landing.js";

function checkPixels(pixels) {
  const context = {
    drawImage: jest.fn(),
    getImageData: () => ({ data: new Uint8ClampedArray(pixels) }),
  };
  return hasUsableImageFrame({
    complete: true,
    naturalWidth: 1600,
    naturalHeight: 1057,
    _landingProbeContext: context,
  });
}
function solid(r, g, b) {
  return Array.from({ length: 48 * 32 }, () => [r, g, b, 255]).flat();
}

test("rejects the actual blank Hubitat capture, including its bright corner buttons", () => {
  const pixels = JSON.parse(
    readFileSync(new URL("./hubitat-blank-pixels.json", import.meta.url)),
  );
  expect(checkPixels(pixels)).toBe(false);
});
test("still rejects black frames", () =>
  expect(checkPixels(solid(0, 0, 0))).toBe(false));
test("preserves dark frames with visible detail", () => {
  const pixels = Array.from({ length: 48 * 32 }, (_, i) =>
    i % 4 ? [15, 20, 25, 255] : [130, 140, 150, 255],
  ).flat();
  expect(checkPixels(pixels)).toBe(true);
});
test("preserves bright scenes", () =>
  expect(checkPixels(solid(160, 170, 180))).toBe(true));
test("does not classify an image before it loads", () => {
  expect(hasUsableImageFrame({ complete: false })).toBe(null);
});

test("holds a truly blank scene without spinning through the rotation", async () => {
  const { initLanding } = await import("../../app/static/js/landing.js");
  jest.useFakeTimers();
  window.__GLIMPSER_DISABLE_BEACONS = true;
  Object.defineProperty(document, "hidden", {
    configurable: true,
    value: false,
  });
  document.body.innerHTML = `<main data-landing-screen><div class="landing-stage-shell" data-landing-rotation-ms="1000" data-landing-refresh-ms="0">
    ${["blank", "camera", "dashboard"].map((id, i) => `<section id="${id}" class="landing-scene ${i === 0 ? "is-visible" : ""}"><div class="landing-hero-media"><img></div></section>`).join("")}
  </div></main>`;
  for (const image of document.querySelectorAll("img")) {
    Object.defineProperties(image, {
      complete: { value: true },
      naturalWidth: { value: 1600 },
      naturalHeight: { value: 1057 },
    });
    const pixels =
      image.closest("section").id === "blank"
        ? solid(31, 41, 55)
        : solid(160, 170, 180);
    image._landingProbeContext = {
      drawImage: () => {},
      getImageData: () => ({ data: new Uint8ClampedArray(pixels) }),
    };
  }
  initLanding();
  document.dispatchEvent(new Event("DOMContentLoaded"));
  jest.advanceTimersByTime(200);
  expect(document.querySelector(".is-visible").id).toBe("blank");
  expect(document.querySelector(".kiosk-offline-view")).not.toBeNull();
  jest.advanceTimersByTime(1000);
  expect(document.querySelector(".is-visible").id).toBe("blank");
  window.dispatchEvent(new Event("pagehide"));
  jest.useRealTimers();
});

test("preserves the actual dark bandwidth chart with thin grid lines", () => {
  const pixels = JSON.parse(
    readFileSync(new URL("./bandwidth-pixels.json", import.meta.url)),
  );
  let width;
  const context = {
    drawImage: (_image, _x, _y, w) => {
      width = w;
    },
    getImageData: () => ({
      data: new Uint8ClampedArray(pixels[String(width)]),
    }),
  };
  expect(
    hasUsableImageFrame({
      complete: true,
      naturalWidth: 900,
      naturalHeight: 260,
      _landingProbeContext: context,
    }),
  ).toBe(true);
});

test("short timelapses preserve normal scene dwell", () => {
  expect(timelapseSceneDwellMs(40000, 5)).toBe(40000);
  expect(timelapseSceneDwellMs(68000, 8)).toBe(68000);
  expect(timelapseSceneDwellMs(40000, 50)).toBe(51000);
});

test("routine events wait for the scene dwell while priority arrivals can interrupt", () => {
  expect(canInterruptScene(false, 1000, 40000, 16000)).toBe(false);
  expect(canInterruptScene(false, 1000, 40000, 41000)).toBe(true);
  expect(canInterruptScene(true, 1000, 40000, 16000)).toBe(true);
});
