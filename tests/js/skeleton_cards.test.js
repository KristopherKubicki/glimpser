import { jest } from "@jest/globals";

document.body.innerHTML = `
  <div id="template-list"></div>
  <div class="template-container"></div>
  <table id="captions-table"></table>
  <select id="group-dropdown"></select>
  <input id="grid-width-slider" type="range">
`;

let loadTemplates;

beforeAll(async () => {
  const mod = await import("../../app/static/js/templates.js");
  loadTemplates = mod.loadTemplates;
});

test("skeletons appear and clear on index", async () => {
  global.fetch = jest.fn(() =>
    Promise.resolve({
      ok: true,
      headers: { get: () => "application/json" },
      json: () => Promise.resolve({}),
    }),
  );
  const promise = loadTemplates();
  expect(document.querySelectorAll(".skeleton-card").length).toBeGreaterThan(0);
  await promise;
  expect(document.querySelectorAll(".skeleton-card").length).toBe(0);
});

test("skeletons appear and clear on captions", async () => {
  global.fetch = jest.fn(() =>
    Promise.resolve({
      ok: true,
      headers: { get: () => "application/json" },
      json: () => Promise.resolve({}),
    }),
  );
  document.querySelector(".template-container").innerHTML = "";
  const promise = loadTemplates();
  expect(document.querySelectorAll(".skeleton-card").length).toBeGreaterThan(0);
  await promise;
  expect(document.querySelectorAll(".skeleton-card").length).toBe(0);
});
