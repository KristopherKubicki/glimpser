import { openDoorNote } from "../../app/static/js/kiosk_indicators.js";

function observation(site, now = 1000) {
  return {
    server_time: now,
    perimeter: {
      site,
      checked_at: now,
      sensors: [
        { attribute: "contact", state: "open", changed_at: 700, label: "Entrance" },
      ],
    },
  };
}

test("door notes use the configured site instead of installation defaults", () => {
  expect(openDoorNote(observation("Example property"), 1000)).toBe(
    "Example property · Entrance · open 5m",
  );
});

test("missing site and stale observations do not identify a property", () => {
  expect(openDoorNote(observation(""), 1000)).toBe("");
  expect(openDoorNote(observation("Example", 800), 1000)).toBe("");
});
