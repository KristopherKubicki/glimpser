import { jest } from "@jest/globals";
import { mountKioskIndicators } from "../../app/static/js/kiosk_indicators.js";
let dispose;
const payload = (events = [], privacy = "inactive") => ({
  available: true,
  privacy,
  server_time: Date.now() / 1000,
  events,
});
const event = (kind = "door", id = "event-1", age = 0) => ({
  id,
  kind,
  label: "Front Door",
  at: Date.now() / 1000 - age,
});
const respond = (data) =>
  fetch.mockResolvedValue({ ok: true, json: async () => data });
beforeEach(() => {
  jest.useFakeTimers();
  jest.setSystemTime(1800000000000);
  Object.defineProperty(document, "hidden", {
    configurable: true,
    value: false,
  });
  localStorage.clear();
  document.body.innerHTML = "";
  global.fetch = jest.fn();
});
afterEach(() => {
  dispose?.();
  dispose = null;
  jest.useRealTimers();
});
test("fresh door signal shows once and clears without replay", async () => {
  respond(payload([event()]));
  dispose = mountKioskIndicators("office");
  await jest.advanceTimersByTimeAsync(0);
  expect(document.querySelector("[role=status]").textContent).toBe(
    "Front Door opened",
  );
  await jest.advanceTimersByTimeAsync(6000);
  expect(document.querySelector("[role=status]").hidden).toBe(true);
  dispose();
  dispose = mountKioskIndicators("office");
  await jest.advanceTimersByTimeAsync(0);
  expect(document.querySelector("[role=status]").hidden).toBe(true);
});
test("stale events never replay, sms contents are generic, multiple events serialize", async () => {
  respond(
    payload([
      event("person", "old", 11),
      event("sms", "new"),
      event("package", "pkg"),
    ]),
  );
  dispose = mountKioskIndicators("living");
  await jest.advanceTimersByTimeAsync(0);
  expect(document.querySelector("[role=status]").textContent).toBe("Text sent");
  await jest.advanceTimersByTimeAsync(4500);
  expect(document.querySelector("[role=status]").textContent).toBe(
    "Package detected",
  );
});
test("privacy is office-only and failures mean unknown", async () => {
  respond(payload([], "active"));
  dispose = mountKioskIndicators("office");
  await jest.advanceTimersByTimeAsync(0);
  expect(document.querySelector(".kiosk-indicator-state").textContent).toBe(
    "Privacy mode on",
  );
  fetch.mockRejectedValue(new Error("offline"));
  await jest.advanceTimersByTimeAsync(1000);
  expect(document.querySelector(".kiosk-indicator-state").textContent).toBe(
    "Indicator connection unavailable",
  );
  dispose();
  respond(payload([], "active"));
  dispose = mountKioskIndicators("living");
  await jest.advanceTimersByTimeAsync(0);
  expect(document.querySelector(".kiosk-indicator-state").hidden).toBe(true);
});
test("late fetch completion cannot update a disposed screen", async () => {
  let finish;
  fetch.mockImplementation(
    () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
  );
  dispose = mountKioskIndicators("office");
  dispose();
  finish({ ok: true, json: async () => payload([event()]) });
  await jest.advanceTimersByTimeAsync(10000);
  expect(document.querySelector(".kiosk-indicators")).toBeNull();
  expect(fetch).toHaveBeenCalledTimes(1);
});
