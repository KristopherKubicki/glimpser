import { jest } from "@jest/globals";

document.body.innerHTML = `
  <div id="template-list"></div>
  <select id="group-dropdown"></select>
  <input id="grid-width-slider" type="range">
`;

let loadTemplates;

beforeAll(async () => {
  const mod = await import("../../app/static/js/templates.js");
  loadTemplates = mod.loadTemplates;
});

test("loads clip when video becomes visible", async () => {
  let callback;
  window.IntersectionObserver = class {
    constructor(cb) {
      callback = cb;
    }
    observe() {}
    unobserve() {}
    disconnect() {}
  };

  global.fetch = jest.fn().mockResolvedValueOnce({
    ok: true,
    headers: { get: () => "application/json" },
    json: () =>
      Promise.resolve({
        cam1: {
          url: "#",
          capture_failed: false,
          last_caption: "",
          last_screenshot_time: 0,
        },
      }),
  });

  await loadTemplates();
  const video = document.querySelector("video");
  const source = video.querySelector("source");
  expect(source.src).toMatch(/\/last_video\/cam1$/);
  expect(video.dataset.hdSrc).toBe("/clip/cam1");

  callback([{ target: video, isIntersecting: true }]);

  expect(source.src).toMatch(/\/last_video\/cam1$/);

  video.dispatchEvent(new Event("mouseenter"));

  expect(source.src).toMatch(/\/clip\/cam1$/);
});
