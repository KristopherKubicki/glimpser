import { historyLabel } from "../../app/static/js/timelapse_preview.js";

test("long history uses hours and dated time bounds", () => {
  const end = Date.UTC(2026, 8, 29, 18) / 1000;
  const label = historyLabel(end - 86400, end);
  expect(label).toContain("24.0 HOURS OF HISTORY");
  expect(label).toContain("28");
  expect(label).toContain("29");
  expect(label).toContain("sampled, recorded");
});

test("short available history is labeled honestly", () => {
  const end = Date.UTC(2026, 8, 29, 18) / 1000;
  expect(historyLabel(end - 1800, end)).toContain("30 MIN OF HISTORY");
});
