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
  expect(safeMediaUrl("/clip/camera")).toBe(`${window.location.origin}/clip/camera`);
  expect(safeMediaUrl("https://example.com/image.png")).toBe("https://example.com/image.png");
  expect(captureImageUrl("/last_screenshot/camera", "saved")).toBe(`${window.location.origin}/last_screenshot/camera?capture=saved`);
});


test("same-origin double slash paths retain their validated origin", () => {
  const url = `${window.location.origin}//untrusted.example/image.png`;
  expect(safeMediaUrl(url)).toBe(url);
  expect(captureImageUrl(url, "saved")).toBe(url);
});
