import { jest } from "@jest/globals";

document.body.innerHTML = `
  <div id="template-list"></div>
  <select id="group-dropdown"></select>
  <input id="grid-width-slider" type="range">
`;

global.slider = document.getElementById("grid-width-slider");

let loadTemplates;
let NO_TIMESTAMP_PLACEHOLDER;

beforeAll(async () => {
  const mod = await import("../../app/static/js/templates.js");
  loadTemplates = mod.loadTemplates;
  NO_TIMESTAMP_PLACEHOLDER = mod.NO_TIMESTAMP_PLACEHOLDER;
});

global.fetch = jest.fn();

describe("loadTemplates placeholder timestamp", () => {
  test("inserts placeholder when timestamp missing", async () => {
    global.fetch.mockResolvedValueOnce({
      ok: true,
      headers: { get: () => "application/json" },
      json: () =>
        Promise.resolve({
          cam1: { url: "#", capture_failed: false, last_caption: "" },
        }),
    });

    await loadTemplates();
    const container = document.querySelector(".video-container");
    expect(container.getAttribute("data-timestamp")).toBe(
      NO_TIMESTAMP_PLACEHOLDER,
    );
  });
});
