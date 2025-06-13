import { jest } from "@jest/globals";

document.body.innerHTML = `
  <select id="nav-group-dropdown"></select>
  <select id="nav-camera-dropdown"></select>
  <nav></nav>
`;

let initNav;

beforeAll(async () => {
  global.fetch = jest.fn(() =>
    Promise.resolve({
      ok: true,
      headers: { get: () => "application/json" },
      json: () => Promise.resolve(["all"]),
    }),
  );
  global.setInterval = jest.fn();
  const mod = await import("../../app/static/js/nav.js");
  initNav = mod.initNav;
});

describe("nav group dropdown", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    Object.defineProperty(window, "location", {
      writable: true,
      configurable: true,
      value: { pathname: "/", href: "" },
    });
  });

  function setup() {
    initNav();
    document.dispatchEvent(new Event("DOMContentLoaded"));
    return document.getElementById("nav-group-dropdown");
  }

  test("placeholder acts like All", () => {
    const dd = setup();
    dd.value = "";
    dd.dispatchEvent(new Event("change"));
    expect(window.location.href).toBe("/live");
  });

  test("selecting all navigates to live", () => {
    const dd = setup();
    dd.value = "all";
    dd.dispatchEvent(new Event("change"));
    expect(window.location.href).toBe("/live");
  });

  test("live page uses changeGroup", () => {
    window.changeGroup = jest.fn();
    const dd = setup();
    window.location.pathname = "/live";
    dd.value = "kitchen";
    dd.dispatchEvent(new Event("change"));
    expect(window.changeGroup).toHaveBeenCalled();
    expect(window.location.href).toBe("");
  });
});
