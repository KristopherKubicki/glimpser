import { jest } from "@jest/globals";

let initKeyVisibility;

beforeAll(async () => {
  const mod = await import("../../app/static/js/key_visibility.js");
  initKeyVisibility = mod.initKeyVisibility;
});

test("toggle switches input type and icon", () => {
  document.body.innerHTML = `
    <input id="API_KEY" type="password" />
    <button class="toggle-key-visibility" data-input="API_KEY" data-sprite="icon.svg">
      <svg><use href="icon.svg#eye"></use></svg>
    </button>
  `;
  initKeyVisibility();
  document.dispatchEvent(new Event("DOMContentLoaded"));
  const btn = document.querySelector(".toggle-key-visibility");
  const input = document.getElementById("API_KEY");
  const useEl = btn.querySelector("use");
  btn.click();
  expect(input.type).toBe("text");
  expect(useEl.getAttribute("href")).toBe("icon.svg#eye-off");
  btn.click();
  expect(input.type).toBe("password");
  expect(useEl.getAttribute("href")).toBe("icon.svg#eye");
});
