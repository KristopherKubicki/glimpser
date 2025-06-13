import { jest } from "@jest/globals";

document.body.innerHTML = `
  <a id="live"></a>
  <nav></nav>
`;

let initNav;

beforeAll(async () => {
  global.fetch = jest.fn(() =>
    Promise.resolve({
      ok: true,
      headers: { get: () => "application/json" },
      json: () => Promise.resolve([]),
    }),
  );
  global.setInterval = jest.fn();
  const mod = await import("../../app/static/js/nav.js");
  initNav = mod.initNav;
});

beforeEach(() => {
  jest.clearAllMocks();
  document.getElementById("live").href = "";
});

test("live link uses camera when set", () => {
  window.currentCamera = "cam1";
  window.currentGroup = "front";
  initNav();
  document.dispatchEvent(new Event("DOMContentLoaded"));
  expect(document.getElementById("live").getAttribute("href")).toBe(
    "/live?camera=cam1",
  );
});

test("live link falls back to group", () => {
  delete window.currentCamera;
  window.currentGroup = "front";
  initNav();
  document.dispatchEvent(new Event("DOMContentLoaded"));
  expect(document.getElementById("live").getAttribute("href")).toBe(
    "/live?group=front",
  );
});

test("live link defaults to /live", () => {
  delete window.currentCamera;
  window.currentGroup = "all";
  initNav();
  document.dispatchEvent(new Event("DOMContentLoaded"));
  expect(document.getElementById("live").getAttribute("href")).toBe("/live");
});
