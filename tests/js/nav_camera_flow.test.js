import { jest } from "@jest/globals";

document.body.innerHTML = `
  <a id="live"></a>
  <select id="nav-group-dropdown"></select>
  <select id="nav-camera-dropdown"></select>
  <nav></nav>
`;

let initNav;

beforeAll(async () => {
  global.fetch = jest.fn((url) => {
    if (String(url).startsWith("/groups")) {
      return Promise.resolve({
        ok: true,
        headers: { get: () => "application/json" },
        json: () => Promise.resolve(["all", "yard"]),
      });
    }
    if (String(url).startsWith("/templates?group=yard")) {
      return Promise.resolve({
        ok: true,
        headers: { get: () => "application/json" },
        json: () => Promise.resolve({ Driveway: {}, FrontDoor: {} }),
      });
    }
    return Promise.resolve({
      ok: true,
      headers: { get: () => "application/json" },
      json: () => Promise.resolve({}),
    });
  });
  global.setInterval = jest.fn();
  const mod = await import("../../app/static/js/nav.js");
  initNav = mod.initNav;
});

beforeEach(() => {
  jest.clearAllMocks();
  Object.defineProperty(window, "location", {
    writable: true,
    configurable: true,
    value: { pathname: "/group/yard", href: "" },
  });
  window.currentGroup = "yard";
  window.currentCamera = null;
});

test("camera dropdown includes all rotator and navigates to /live", async () => {
  initNav();
  document.dispatchEvent(new Event("DOMContentLoaded"));
  await Promise.resolve();
  await Promise.resolve();

  const cam = document.getElementById("nav-camera-dropdown");
  expect(cam.querySelector('option[value="__all_rotator__"]')).not.toBeNull();

  cam.value = "__all_rotator__";
  cam.dispatchEvent(new Event("change"));
  expect(window.location.href).toBe("/live?rotator=all");
});
