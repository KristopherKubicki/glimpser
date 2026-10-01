import { canHandoffToDoor } from "../../app/static/js/priority_handoff.js";
const now = Date.parse("2026-09-27T17:00:00Z");
const previous = {
  priority: true,
  camera_name: "ExampleApproach",
  key: "a",
  occurred_at: "2026-09-27 16:59:30",
};
const next = {
  priority: true,
  camera_name: "ExampleDoor",
  key: "b",
  occurred_at: "2026-09-27 16:59:45",
};
test("fresh configured door supersedes approach", () => {
  expect(canHandoffToDoor(next, previous, now)).toBe(true);
  expect(
    canHandoffToDoor(next, { ...previous, camera_name: "ExampleGarage" }, now),
  ).toBe(true);
});
test.each([
  { key: "a" },
  { priority: false },
  { camera_name: "ExampleApproach" },
  { camera_name: "OtherDoor" },
  { occurred_at: "invalid" },
  { occurred_at: "2026-09-27 16:59:30" },
  { occurred_at: "2026-09-27 16:59:00" },
  { occurred_at: "2026-09-27 17:00:01" },
  { occurred_at: "2026-09-27 16:57:00" },
])(
  "rejects duplicate, older, stale, future, or unrelated event %j",
  (change) => {
    expect(canHandoffToDoor({ ...next, ...change }, previous, now)).toBe(false);
  },
);
test("never steals another property's alert or reverses door to driveway", () => {
  expect(
    canHandoffToDoor(next, { ...previous, camera_name: "OtherApproach" }, now),
  ).toBe(false);
  expect(canHandoffToDoor(previous, next, now)).toBe(false);
  expect(canHandoffToDoor(next, null, now)).toBe(false);
});

beforeEach(() => {
  document.body.innerHTML =
    '<script id="priority-handoff-settings" type="application/json"></script>';
  document.getElementById("priority-handoff-settings").textContent =
    JSON.stringify({ ExampleDoor: ["ExampleApproach", "ExampleGarage"] });
});
test.each(["{}", "invalid", "null", '{"ExampleDoor":"ExampleApproach"}'])(
  "invalid or missing rules cannot interrupt an alert: %s",
  (rules) => {
    document.getElementById("priority-handoff-settings").textContent = rules;
    expect(canHandoffToDoor(next, previous, now)).toBe(false);
  },
);
