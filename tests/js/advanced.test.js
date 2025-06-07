import { jest } from "@jest/globals";

document.body.innerHTML = `
  <button id="advanced-toggle"></button>
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

test("click toggles advanced state and stores it", () => {
  initAdvanced();
  document.dispatchEvent(new Event("DOMContentLoaded"));
  document.getElementById("advanced-toggle").click();
  expect(document.body.classList.contains("advanced-enabled")).toBe(true);
  expect(sessionStorage.getItem("advanced-enabled")).toBe("true");
});

test("initial state reads from sessionStorage", () => {
  sessionStorage.setItem("advanced-enabled", "true");
  initAdvanced();
  document.dispatchEvent(new Event("DOMContentLoaded"));
  expect(document.body.classList.contains("advanced-enabled")).toBe(true);
});
