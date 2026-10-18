import { jest } from "@jest/globals";
import { initLanding } from "../../app/static/js/landing.js";

test.each([
  { available: ["TestB"], clears: true },
  { available: [], clears: true },
  { available: null, clears: false },
])(
  "failed held camera clears hold when available=%j",
  async ({ available: availableAfterFailure, clears }) => {
    jest.useFakeTimers();
    window.localStorage.clear();
    window.__GLIMPSER_DISABLE_BEACONS = true;
    Object.defineProperty(document, "hidden", {
      configurable: true,
      value: false,
    });
    const originalFetch = window.fetch;
    let available = ["TestA", "TestB"];
    window.fetch = jest.fn(async () => ({
      ok: true,
      json: async () => ({
        events: [],
        available_cameras: available,
      }),
    }));
    document.body.innerHTML = `<main data-landing-screen>
    <div data-landing-review-controls>
      <button data-review-action="hold">Hold</button>
      <select data-review-duration><option value="300000">5m</option></select>
      <span data-review-status></span>
    </div>
    <div class="landing-stage-shell" data-landing-profile="hal" data-landing-events-enabled="true" data-landing-events-url="/events-test" data-landing-events-poll-ms="1000" data-landing-rotation-ms="20000" data-landing-refresh-ms="0">
      ${["TestA", "TestB"].map((name, i) => `<section id="${name}" data-scene-id="${name}" data-hero-name="${name}" class="landing-scene ${i === 0 ? "is-visible" : ""}"><div class="landing-hero-media"><img></div></section>`).join("")}
    </div>
  </main>`;
    for (const img of document.querySelectorAll("img")) {
      Object.defineProperties(img, {
        complete: { value: true },
        naturalWidth: { value: 1600 },
        naturalHeight: { value: 1057 },
      });
      img._landingProbeContext = {
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
      await jest.advanceTimersByTimeAsync(100);
      document.querySelector('[data-review-action="hold"]').click();
      available = availableAfterFailure;
      await jest.advanceTimersByTimeAsync(6000);
      if (!clears) {
        expect(
          document
            .querySelector('[data-review-action="hold"]')
            .getAttribute("aria-pressed"),
        ).toBe("true");
        expect(
          localStorage.getItem("glimpser.manual-hold.v1.hal"),
        ).not.toBeNull();
        return;
      }
      expect(
        document
          .querySelector('[data-review-action="hold"]')
          .getAttribute("aria-pressed"),
      ).toBe("false");
      expect(localStorage.getItem("glimpser.manual-hold.v1.hal")).toBeNull();
      available = ["TestB"];
      await jest.advanceTimersByTimeAsync(6000);
      expect(document.querySelector(".is-visible").id).toBe("TestB");
      available = ["TestA", "TestB"];
      await jest.advanceTimersByTimeAsync(1000);
      expect(
        document
          .querySelector('[data-review-action="hold"]')
          .getAttribute("aria-pressed"),
      ).toBe("false");
    } finally {
      window.dispatchEvent(new Event("pagehide"));
      window.fetch = originalFetch;
      jest.useRealTimers();
    }
  },
);
