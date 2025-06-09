import { jest } from "@jest/globals";

let initUnsavedIndicator;

beforeAll(async () => {
  const mod = await import("../../app/static/js/unsaved.js");
  initUnsavedIndicator = mod.initUnsavedIndicator;
});

test("icon shows on input and hides on submit", () => {
  document.body.innerHTML = `
    <form id="settings-form">
      <input id="foo" />
    </form>
    <svg id="unsaved-icon" class="hidden"></svg>
  `;
  initUnsavedIndicator();
  document.dispatchEvent(new Event("DOMContentLoaded"));
  const input = document.getElementById("foo");
  const icon = document.getElementById("unsaved-icon");
  input.value = "bar";
  input.dispatchEvent(new Event("input", { bubbles: true }));
  expect(icon.classList.contains("hidden")).toBe(false);
  document.getElementById("settings-form").dispatchEvent(new Event("submit"));
  expect(icon.classList.contains("hidden")).toBe(true);
});
