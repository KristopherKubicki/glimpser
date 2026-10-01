import {
  createHistoryMemory,
  preferCurrentView,
  timelapseIsDue,
  historyLabel,
} from "../../app/static/js/timelapse_preview.js";

test("history gets a turn, then current view gets a turn even if history was unavailable", () => {
  expect(preferCurrentView(true, null, null, false)).toBe(false);
  expect(preferCurrentView(true, 100, null, false)).toBe(true);
  expect(preferCurrentView(true, 100, 200, false)).toBe(false);
  expect(preferCurrentView(false, 100, 200, false)).toBe(true);
  expect(preferCurrentView(true, null, null, true)).toBe(true);
});

test("history cooldown leaves room for current views", () => {
  expect(timelapseIsDue(null, 0)).toBe(true);
  expect(timelapseIsDue(1000, 30000)).toBe(false);
  expect(timelapseIsDue(1000, 61000)).toBe(true);
});

test("skip nearly identical history, allow meaningful new history and expire suppression", () => {
  const memory = createHistoryMemory();
  expect(memory.repeats("camera", 100, 3700, 0)).toBe(false);
  memory.remember("camera", 100, 3700, 0);
  expect(memory.repeats("camera", 100, 3700, 1000)).toBe(true);
  expect(memory.repeats("camera", 160, 3760, 1000)).toBe(true);
  expect(memory.repeats("other", 100, 3700, 1000)).toBe(false);
  expect(memory.repeats("camera", 100, 4100, 1000)).toBe(false);
  expect(memory.repeats("camera", 100, 3700, 600000)).toBe(false);
});

test("history memory evicts old cameras instead of growing without bound", () => {
  const memory = createHistoryMemory();
  for (let i = 0; i < 129; i++) memory.remember(String(i), 100, 3700, 0);
  expect(memory.repeats("0", 100, 3700, 100)).toBe(false);
  expect(memory.repeats("128", 100, 3700, 100)).toBe(true);
});

test("short history is disclosed without guessing why it is missing", () => {
  const end = Date.UTC(2026, 8, 29, 18) / 1000;
  expect(historyLabel(end - 3600, end)).toContain("shorter available history");
  expect(historyLabel(end - 86400, end)).not.toContain(
    "shorter available history",
  );
});
