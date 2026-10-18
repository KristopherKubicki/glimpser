import { jest } from "@jest/globals";
import { readFileSync } from "node:fs";
import { hasUsableImageFrame } from "../../app/static/js/landing.js";

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

test("holds a blank scene, then resumes rotation after a usable frame arrives", async () => {
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
  const recovered = document.querySelector("#blank img");
  recovered._landingProbeContext.getImageData = () => ({
    data: new Uint8ClampedArray(solid(160, 170, 180)),
  });
  recovered.dispatchEvent(new Event("load"));
  expect(document.querySelector(".kiosk-offline-view")).toBeNull();
  jest.advanceTimersByTime(1000);
  expect(document.querySelector(".is-visible").id).toBe("camera");
  window.dispatchEvent(new Event("pagehide"));
  jest.useRealTimers();
});

test("touch controls navigate, hold, resume, and expose recent scenes", async () => {
  const { initLanding } = await import("../../app/static/js/landing.js");
  jest.useFakeTimers();
  localStorage.clear();
  window.__GLIMPSER_DISABLE_BEACONS = true;
  Object.defineProperty(document, "hidden", {
    configurable: true,
    value: false,
  });
  document.body.innerHTML = `<main data-landing-screen>
    <div data-landing-review-controls>
      <button data-review-action="previous">Previous</button>
      <select data-review-duration><option value="300000">5m</option></select>
      <button data-review-action="hold">Hold</button>
      <button data-review-action="next">Next</button>
      <button data-review-action="recent">Recent</button>
      <span data-review-status></span>
      <div data-review-recent hidden></div>
    </div>
    <div class="landing-stage-shell" data-landing-profile="living" data-landing-rotation-ms="1000" data-landing-refresh-ms="0">
      ${["one", "two", "three"].map((id, i) => `<section id="${id}" data-scene-id="${id}" data-hero-name="Camera ${id}" class="landing-scene ${i === 0 ? "is-visible" : ""}"><div class="landing-hero-media"><img></div></section>`).join("")}
    </div>
  </main>`;
  for (const image of document.querySelectorAll("img")) {
    Object.defineProperties(image, {
      complete: { value: true },
      naturalWidth: { value: 1600 },
      naturalHeight: { value: 1057 },
    });
    image._landingProbeContext = {
      drawImage: () => {},
      getImageData: () => ({
        data: new Uint8ClampedArray(solid(160, 170, 180)),
      }),
    };
  }
  initLanding();
  document.dispatchEvent(new Event("DOMContentLoaded"));

  document.querySelector('[data-review-action="next"]').click();
  expect(document.querySelector(".is-visible").id).toBe("two");
  document.querySelector('[data-review-action="hold"]').click();
  expect(
    document.querySelector('[data-review-action="hold"]').textContent,
  ).toBe("Resume");
  jest.advanceTimersByTime(2000);
  expect(document.querySelector(".is-visible").id).toBe("two");

  const click = (action) =>
    document.querySelector(`[data-review-action="${action}"]`).click();
  click("next");
  expect(document.querySelector(".is-visible").id).toBe("three");
  click("previous");
  expect(document.querySelector(".is-visible").id).toBe("two");
  click("previous");
  expect(document.querySelector(".is-visible").id).toBe("one");
  document.dispatchEvent(
    new KeyboardEvent("keydown", { key: "ArrowRight", bubbles: true }),
  );
  expect(document.querySelector(".is-visible").id).toBe("two");
  document
    .querySelector("select")
    .dispatchEvent(
      new KeyboardEvent("keydown", { key: "ArrowRight", bubbles: true }),
    );
  expect(document.querySelector(".is-visible").id).toBe("two");
  expect(
    document
      .querySelector('[data-review-action="hold"]')
      .getAttribute("aria-pressed"),
  ).toBe("true");

  document.querySelector('[data-review-action="recent"]').click();
  expect(document.querySelector("[data-review-recent]").hidden).toBe(false);
  expect(document.querySelectorAll("[data-review-recent] button")).toHaveLength(
    3,
  );

  document.querySelector('[data-review-action="hold"]').click();
  jest.advanceTimersByTime(1000);
  expect(document.querySelector(".is-visible").id).toBe("three");
  window.dispatchEvent(new Event("pagehide"));
  jest.useRealTimers();
});
