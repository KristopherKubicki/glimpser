import { jest } from "@jest/globals";

const html = `<div id="controls-wrapper"></div>`;
document.body.innerHTML = html;

jest.useFakeTimers();

let initControlsDropdown;

beforeAll(async () => {
  ({ initControlsDropdown } = await import("../../app/static/js/controls.js"));
});

describe("controls dropdown", () => {
  beforeEach(() => {
    document.body.innerHTML = html;
    jest.clearAllMocks();
    window.matchMedia = jest.fn().mockImplementation(() => ({
      matches: false,
      addListener: jest.fn(),
      removeListener: jest.fn(),
    }));
  });
  test("fades out after inactivity on desktop", () => {
    const wrapper = document.getElementById("controls-wrapper");
    initControlsDropdown();
    document.dispatchEvent(new Event("DOMContentLoaded"));
    jest.advanceTimersByTime(3000);
    expect(wrapper.classList.contains("fade-out")).toBe(true);
  });

  test("remains visible on mobile", () => {
    window.matchMedia = jest.fn().mockImplementation(() => ({
      matches: true,
      addListener: jest.fn(),
      removeListener: jest.fn(),
    }));
    const wrapper = document.getElementById("controls-wrapper");
    initControlsDropdown();
    document.dispatchEvent(new Event("DOMContentLoaded"));
    jest.advanceTimersByTime(5000);
    expect(wrapper.classList.contains("fade-out")).toBe(false);
  });
});
