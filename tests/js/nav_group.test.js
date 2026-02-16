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
    expect(window.location.href).toBe("/");
  });

  test("selecting all navigates to live", () => {
    const dd = setup();
    dd.value = "all";
    dd.dispatchEvent(new Event("change"));
    expect(window.location.href).toBe("/");
  });

  test("selecting a group navigates to group wall", () => {
    const dd = setup();
    window.location.pathname = "/live";
    const opt = document.createElement("option");
    opt.value = "kitchen";
    opt.textContent = "kitchen";
    dd.appendChild(opt);
    dd.value = "kitchen";
    dd.dispatchEvent(new Event("change"));
    expect(window.location.href).toBe("/group/kitchen");
  });
});
