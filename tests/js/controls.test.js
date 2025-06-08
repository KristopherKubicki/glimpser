import { jest } from "@jest/globals";

document.body.innerHTML = `
  <details id="controls-wrapper">
    <summary>Controls</summary>
  </details>
`;

jest.useFakeTimers();

let initControlsDropdown;

beforeAll(async () => {
  ({ initControlsDropdown } = await import("../../app/static/js/controls.js"));
});

describe("controls dropdown", () => {
  test("auto collapses after inactivity", () => {
    const details = document.getElementById("controls-wrapper");
    details.setAttribute("open", "");
    initControlsDropdown();
    document.dispatchEvent(new Event("DOMContentLoaded"));
    jest.advanceTimersByTime(5000);
    expect(details.classList.contains("fade-out")).toBe(true);
    jest.advanceTimersByTime(500);
    expect(details.hasAttribute("open")).toBe(false);
    expect(details.classList.contains("fade-out")).toBe(false);
  });

  test("button shows and hides on activity", () => {
    const details = document.getElementById("controls-wrapper");
    initControlsDropdown();
    document.dispatchEvent(new Event("DOMContentLoaded"));
    expect(details.classList.contains("show-summary")).toBe(true);
    jest.advanceTimersByTime(3000);
    expect(details.classList.contains("show-summary")).toBe(false);
  });
});
