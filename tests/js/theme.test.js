import { jest } from "@jest/globals";

document.body.innerHTML = `
  <a id="theme-toggle"><svg><use href="#sun"></use></svg></a>
  <button id="gen-tab" class="tab-link" data-tab="General-tab"></button>
`;

Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: () => ({ matches: false }),
});

let initThemeToggle;

beforeAll(async () => {
  const mod = await import("../../app/static/js/theme.js");
  initThemeToggle = mod.initThemeToggle;
});

beforeEach(() => {
  localStorage.clear();
  jest.clearAllMocks();
});

test("clicking toggle switches theme and activates General tab", () => {
  const btn = document.getElementById("gen-tab");
  btn.click = jest.fn();
  initThemeToggle();
  document.dispatchEvent(new Event("DOMContentLoaded"));
  document.getElementById("theme-toggle").click();
  expect(localStorage.getItem("theme")).toBe("light");
  expect(btn.click).toHaveBeenCalled();
});
