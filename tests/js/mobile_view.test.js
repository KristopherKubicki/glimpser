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

global.fetch = jest.fn();

beforeEach(() => {
  jest.clearAllMocks();
  window.matchMedia = jest.fn().mockImplementation(() => ({
    matches: true,
    addListener: jest.fn(),
    removeListener: jest.fn(),
  }));
});

test("mobile view displays preview video", async () => {
  global.fetch.mockResolvedValueOnce({
    ok: true,
    headers: { get: () => "application/json" },
    json: () =>
      Promise.resolve({
        cam1: { url: "#", capture_failed: false, last_caption: "" },
      }),
  });

  await loadTemplates();

  const card = document.querySelector(".mobile-card");
  expect(card).not.toBeNull();
  expect(card.querySelector("video")).not.toBeNull();
});
