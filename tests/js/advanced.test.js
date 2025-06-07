import { jest } from "@jest/globals";

document.body.innerHTML = `
  <input id="advanced-toggle" type="checkbox" />
`;

let initAdvanced;

beforeAll(async () => {
  const mod = await import("../../app/static/js/advanced.js");
  initAdvanced = mod.initAdvanced;
});

afterEach(() => {
  document.body.classList.remove("advanced-enabled");
  sessionStorage.clear();
});

test("change toggles advanced state and stores it", () => {
  initAdvanced();
  document.dispatchEvent(new Event("DOMContentLoaded"));
  const el = document.getElementById("advanced-toggle");
  el.checked = true;
  el.dispatchEvent(new Event("change"));
  expect(document.body.classList.contains("advanced-enabled")).toBe(true);
  expect(sessionStorage.getItem("advanced-enabled")).toBe("true");
});

test("initial state reads from sessionStorage", () => {
  sessionStorage.setItem("advanced-enabled", "true");
  initAdvanced();
  document.dispatchEvent(new Event("DOMContentLoaded"));
  expect(document.body.classList.contains("advanced-enabled")).toBe(true);
  expect(document.getElementById("advanced-toggle").checked).toBe(true);
});
