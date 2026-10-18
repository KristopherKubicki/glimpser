import { jest } from "@jest/globals";
import {
  initLanding,
  normalizeRecentScenes,
} from "../../app/static/js/landing.js";

test.each(["[null]", "[null,{},123]", "{broken"])(
  "bad recent-view history %s cannot stop a saved hold",
  async (history) => {
    jest.useFakeTimers();
    localStorage.clear();
    window.__GLIMPSER_DISABLE_BEACONS = true;
    Object.defineProperty(document, "hidden", {
      configurable: true,
      value: false,
    });
    localStorage.setItem("glimpser.recent-scenes.v1.hal", history);
    localStorage.setItem(
      "glimpser.manual-hold.v1.hal",
      JSON.stringify({ sceneId: "A", heroName: "A", until: null }),
    );
    document.body.innerHTML = `<main data-landing-screen>
    <div data-landing-review-controls><button data-review-action="hold">Hold</button><span data-review-status></span><div data-review-recent></div></div>
    <div class="landing-stage-shell" data-landing-profile="hal" data-landing-rotation-ms="1000" data-landing-refresh-ms="0">
      ${["A", "B"].map((name, i) => `<section id="${name}" data-scene-id="${name}" data-hero-name="${name}" class="landing-scene ${i === 0 ? "is-visible" : ""}"><div class="landing-hero-media"><img></div></section>`).join("")}
    </div></main>`;
    for (const image of document.querySelectorAll("img")) {
      Object.defineProperties(image, {
        complete: { value: true },
        naturalWidth: { value: 1600 },
        naturalHeight: { value: 1057 },
      });
      image._landingProbeContext = {
        drawImage() {},
        getImageData: () => ({
          data: new Uint8ClampedArray(
            Array.from({ length: 48 * 32 }, () => [160, 170, 180, 255]).flat(),
          ),
        }),
      };
    }
    try {
      initLanding();
      document.dispatchEvent(new Event("DOMContentLoaded"));
      await jest.advanceTimersByTimeAsync(3000);
      expect(
        document
          .querySelector('[data-review-action="hold"]')
          .getAttribute("aria-pressed"),
      ).toBe("true");
      expect(document.querySelector(".is-visible").id).toBe("A");
    } finally {
      window.dispatchEvent(new Event("pagehide"));
      jest.useRealTimers();
    }
  },
);

test("recent-view recovery preserves valid entries and bounds the result", () => {
  expect(
    normalizeRecentScenes([
      null,
      false,
      {},
      { sceneId: "A" },
      { heroName: "B" },
      { sceneId: 3, heroName: [] },
    ]),
  ).toEqual([
    { sceneId: "A", heroName: "" },
    { sceneId: "", heroName: "B" },
  ]);
  expect(normalizeRecentScenes({})).toEqual([]);
  expect(
    normalizeRecentScenes(
      Array.from({ length: 100 }, (_, i) => ({ heroName: String(i) })),
    ),
  ).toHaveLength(8);
});
