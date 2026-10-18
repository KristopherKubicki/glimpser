import { captureImageUrl, safeMediaUrl } from "../../app/static/js/capture_age.js";

test.each(["javascript:alert(1)", "data:text/html,bad", "file:///etc/passwd", "http://["])(
  "rejects unsafe media URL %s even without a capture timestamp",
  (url) => {
    expect(safeMediaUrl(url)).toBe("");
    expect(captureImageUrl(url, null)).toBe("");
    expect(captureImageUrl(url, "2026-10-01T00:00:00Z")).toBe("");
  },
);

test("preserves valid paths and pins the requested capture", () => {
  expect(safeMediaUrl("/clip/camera")).toBe("/clip/camera");
  expect(safeMediaUrl("https://example.com/image.png")).toBe("https://example.com/image.png");
  expect(captureImageUrl("/last_screenshot/camera", "saved")).toBe("/last_screenshot/camera?capture=saved");
});
