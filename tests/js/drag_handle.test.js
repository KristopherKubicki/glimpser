import { jest } from "@jest/globals";

document.body.innerHTML = `
  <div id="template-list"></div>
  <input id="grid-width-slider" type="range" min="50" max="500" value="100">
`;

let initTemplates;
let setupTileResizeDrag;

beforeAll(async () => {
  const mod = await import("../../app/static/js/templates.js");
  initTemplates = mod.initTemplates;
  setupTileResizeDrag = mod.setupTileResizeDrag;
});

function mockBBox(width) {
  return { left: 0, width };
}

test("drag handle adjusts slider", () => {
  global.fetch = jest.fn(() =>
    Promise.resolve({
      ok: true,
      headers: { get: () => "application/json" },
      json: () => Promise.resolve({}),
    }),
  );
  const slider = document.getElementById("grid-width-slider");
  slider.getBoundingClientRect = () => mockBBox(200);
  initTemplates();
  document.dispatchEvent(new Event("DOMContentLoaded"));
  const handle = document.getElementById("tile-drag-handle");
  expect(handle).not.toBeNull();
  const start = new MouseEvent("mousedown", { clientX: 0 });
  handle.dispatchEvent(start);
  document.dispatchEvent(new MouseEvent("mousemove", { clientX: 100 }));
  document.dispatchEvent(new MouseEvent("mouseup"));
  expect(parseFloat(slider.value)).toBeGreaterThan(100);
});
