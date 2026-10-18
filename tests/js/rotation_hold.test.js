import { jest } from "@jest/globals";
import { initLanding } from "../../app/static/js/landing.js";

test.each([
  ["TestA", "dismiss"],
  ["TestA", "expire"],
  ["TestB", "dismiss"],
  ["TestB", "expire"],
])(
  "priority alert at %s returns to the held camera on %s",
  async (target, finish) => {
    jest.useFakeTimers();
    window.localStorage.clear();
    window.__GLIMPSER_DISABLE_BEACONS = true;
    Object.defineProperty(document, "hidden", {
      configurable: true,
      value: false,
    });
    const originalFetch = window.fetch;
    let event = null;
    window.fetch = jest.fn(async () => ({
      ok: true,
      json: async () => ({
        events: event ? [event] : [],
        available_cameras: ["TestA", "TestB"],
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
      event = {
        key: "hold-test",
        priority: true,
        kind: "doorbell",
        camera_name: target,
        interrupt_ms: 10000,
        occurred_at: new Date().toISOString(),
      };
      await jest.advanceTimersByTimeAsync(6000);
      expect(document.querySelector(".kiosk-priority-alert")).not.toBeNull();
      expect(
        document.querySelector(".kiosk-priority-alert button").textContent,
      ).toBe("Return to held view");
      expect(document.querySelector(".is-visible").id).toBe(target);
      if (finish === "dismiss")
        document.querySelector(".kiosk-priority-alert button").click();
      else await jest.advanceTimersByTimeAsync(11000);
      expect(document.querySelector(".is-visible").id).toBe("TestA");
      expect(
        document
          .querySelector('[data-review-action="hold"]')
          .getAttribute("aria-pressed"),
      ).toBe("true");
      await jest.advanceTimersByTimeAsync(25000);
      expect(document.querySelector(".is-visible").id).toBe("TestA");
    } finally {
      window.dispatchEvent(new Event("pagehide"));
      window.fetch = originalFetch;
      jest.useRealTimers();
    }
  },
);
