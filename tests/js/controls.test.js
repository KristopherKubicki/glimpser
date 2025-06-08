import { jest } from "@jest/globals";

document.body.innerHTML = `
  <div id="controls-wrapper" class="closed">
    <button id="controls-toggle" type="button">Controls</button>
  </div>
`;

jest.useFakeTimers();

let initControlsDropdown;

beforeAll(async () => {
  ({ initControlsDropdown } = await import("../../app/static/js/controls.js"));
});

describe("controls dropdown", () => {
  test("auto collapses after inactivity", () => {
    const wrapper = document.getElementById("controls-wrapper");
    wrapper.classList.remove("closed");
    initControlsDropdown();
    document.dispatchEvent(new Event("DOMContentLoaded"));
    jest.advanceTimersByTime(5000);
    expect(wrapper.classList.contains("fade-out")).toBe(true);
    jest.advanceTimersByTime(500);
    expect(wrapper.classList.contains("closed")).toBe(true);
    expect(wrapper.classList.contains("fade-out")).toBe(false);
  });

  test("button shows and hides on activity", () => {
    const wrapper = document.getElementById("controls-wrapper");
    initControlsDropdown();
    document.dispatchEvent(new Event("DOMContentLoaded"));
    expect(wrapper.classList.contains("show-toggle")).toBe(true);
    jest.advanceTimersByTime(3000);
    expect(wrapper.classList.contains("show-toggle")).toBe(false);
  });
});
