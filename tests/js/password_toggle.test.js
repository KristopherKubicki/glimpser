import { jest } from "@jest/globals";

let initPasswordToggle;

beforeAll(async () => {
  const mod = await import("../../app/static/js/password_toggle.js");
  initPasswordToggle = mod.initPasswordToggle;
});

test("click toggles password visibility", () => {
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
  btn.click();
  expect(input.type).toBe("text");
  expect(useEl.getAttribute("href")).toBe("icons.svg#eye-off");
  btn.click();
  expect(input.type).toBe("password");
  expect(useEl.getAttribute("href")).toBe("icons.svg#eye");
});
