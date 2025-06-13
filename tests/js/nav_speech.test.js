import { jest } from "@jest/globals";

document.body.innerHTML = `
  <a id="speech-stop" class="settings-icon" role="button"></a>
  <nav></nav>
`;

let initNav;

beforeAll(async () => {
  global.fetch = jest.fn(() =>
    Promise.resolve({
      ok: true,
      headers: { get: () => "application/json" },
      json: () => Promise.resolve([]),
    }),
  );
  global.setInterval = jest.fn();
  const mod = await import("../../app/static/js/nav.js");
  initNav = mod.initNav;
});

beforeEach(() => {
  jest.clearAllMocks();
  window.speechSynthesis = { speaking: true, cancel: jest.fn() };
});

test("speech icon shows when speaking", () => {
  initNav();
  document.dispatchEvent(new Event("DOMContentLoaded"));
  const icon = document.getElementById("speech-stop");
  expect(icon.style.display).toBe("flex");
});

test("clicking icon cancels speech", () => {
  initNav();
  document.dispatchEvent(new Event("DOMContentLoaded"));
  const icon = document.getElementById("speech-stop");
  icon.click();
  expect(window.speechSynthesis.cancel).toHaveBeenCalled();
});
