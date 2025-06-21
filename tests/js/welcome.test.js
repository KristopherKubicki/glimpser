import { jest } from "@jest/globals";

let initWelcome;

beforeAll(async () => {
  const mod = await import("../../app/static/js/welcome.js");
  initWelcome = mod.initWelcome;
});

beforeEach(() => {
  document.body.innerHTML = `
    <div id="welcome-modal" style="display:none">
      <span id="welcome-close"></span>
      <button id="welcome-ok"></button>
    </div>
  `;
  localStorage.clear();
});

test("shows modal when no templates loaded and not seen", () => {
  initWelcome();
  document.dispatchEvent(new Event("DOMContentLoaded"));
  window.dispatchEvent(
    new CustomEvent("templatesLoaded", { detail: { count: 0 } }),
  );
  const modal = document.getElementById("welcome-modal");
  expect(modal.style.display).toBe("block");
});

test("does not show modal when templates exist or welcome seen", () => {
  initWelcome();
  document.dispatchEvent(new Event("DOMContentLoaded"));
  window.dispatchEvent(
    new CustomEvent("templatesLoaded", { detail: { count: 2 } }),
  );
  const modal = document.getElementById("welcome-modal");
  expect(modal.style.display).toBe("none");
  localStorage.setItem("welcomeSeen", "true");
  window.dispatchEvent(
    new CustomEvent("templatesLoaded", { detail: { count: 0 } }),
  );
  expect(modal.style.display).toBe("none");
});

test("dismiss buttons hide modal and store preference", () => {
  initWelcome();
  document.dispatchEvent(new Event("DOMContentLoaded"));
  window.dispatchEvent(
    new CustomEvent("templatesLoaded", { detail: { count: 0 } }),
  );
  document.getElementById("welcome-close").dispatchEvent(new Event("click"));
  const modal = document.getElementById("welcome-modal");
  expect(modal.style.display).toBe("none");
  expect(localStorage.getItem("welcomeSeen")).toBe("true");
  modal.style.display = "block";
  localStorage.clear();
  document.getElementById("welcome-ok").dispatchEvent(new Event("click"));
  expect(modal.style.display).toBe("none");
  expect(localStorage.getItem("welcomeSeen")).toBe("true");
});
