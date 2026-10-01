import { jest } from "@jest/globals";
import { mountKioskHeartbeat } from "../../app/static/js/kiosk_heartbeat.js";
test("heartbeat waits for a rendered frame and stops on disposal", async () => {
  jest.useFakeTimers();
  let paint;
  global.requestAnimationFrame = jest.fn((fn) => {
    paint = fn;
    return 4;
  });
  global.cancelAnimationFrame = jest.fn();
  global.fetch = jest.fn().mockResolvedValue({ ok: true });
  const dispose = mountKioskHeartbeat("office");
  expect(fetch).not.toHaveBeenCalled();
  paint();
  expect(fetch).toHaveBeenCalledTimes(1);
  dispose();
  jest.advanceTimersByTime(60000);
  expect(fetch).toHaveBeenCalledTimes(1);
  await Promise.resolve();
  jest.useRealTimers();
});
