import { jest } from "@jest/globals";
import { mountAmbientClock } from "../../app/static/js/ambient_clock.js";
test("clock follows live readiness and returns to the saved caption", async () => {
  jest.useFakeTimers();
  document.body.innerHTML =
    '<section class="landing-scene is-visible"><div class="kiosk-caption-strip"></div><div class="kiosk-live-layer"><div class="kiosk-live-label">Door LIVE</div></div></section>';
  const dispose = mountAmbientClock(document.body);
  const clock = document.querySelector(".ambient-clock");
  const scene = document.querySelector("section");
  expect(clock.parentElement.className).toBe("kiosk-caption-strip");
  scene.classList.add("has-kiosk-live");
  await Promise.resolve();
  expect(clock.parentElement.className).toBe("kiosk-live-label");
  expect(clock.hidden).toBe(false);
  scene.querySelector(".kiosk-live-layer").remove();
  scene.classList.remove("has-kiosk-live");
  await Promise.resolve();
  expect(clock.parentElement.className).toBe("kiosk-caption-strip");
  expect(document.querySelectorAll(".ambient-clock")).toHaveLength(1);
  dispose();
  jest.useRealTimers();
});
