import { jest } from "@jest/globals";

document.body.innerHTML = `
  <div id="template-list"></div>
  <select id="group-dropdown"></select>
  <input id="grid-width-slider" type="range">
`;

let loadTemplates;
let cbs;

beforeAll(async () => {
  const mod = await import("../../app/static/js/templates.js");
  loadTemplates = mod.loadTemplates;
});

beforeEach(() => {
  cbs = [];
  window.IntersectionObserver = class {
    constructor(fn) {
      cbs.push(fn);
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
});

test("poster loads when video becomes visible", async () => {
  await loadTemplates();
  const video = document.querySelector("video");
  expect(video.dataset.poster).toBe("/last_screenshot/cam1");
  expect(video.poster).toBe("");
  await Promise.resolve();
  cbs[0]([{ target: video, isIntersecting: true }]);
  expect(video.poster.endsWith("/last_screenshot/cam1")).toBe(true);
});
