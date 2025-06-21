import { jest } from "@jest/globals";

let initPasswordToggle;

beforeAll(async () => {
  const mod = await import("../../app/static/js/password_toggle.js");
  initPasswordToggle = mod.initPasswordToggle;
});

test("password visible while button held", () => {
  document.body.innerHTML = `
    <input id="password" type="password" />
    <button id="password-toggle" aria-label="Show password">
      <svg><use href="icons.svg#eye"></use></svg>
    </button>
  `;
  initPasswordToggle();
  document.dispatchEvent(new Event("DOMContentLoaded"));
  const input = document.getElementById("password");
  const btn = document.getElementById("password-toggle");
  const useEl = btn.querySelector("use");
  btn.dispatchEvent(new Event("mousedown"));
  expect(input.type).toBe("text");
  expect(useEl.getAttribute("href")).toBe("icons.svg#eye-off");
  btn.dispatchEvent(new Event("mouseup"));
  expect(input.type).toBe("password");
  expect(useEl.getAttribute("href")).toBe("icons.svg#eye");
});
