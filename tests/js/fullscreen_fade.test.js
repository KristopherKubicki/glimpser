import { jest } from "@jest/globals";

document.body.innerHTML = `
  <div class="video-container">
    <video id="live-video"></video>
    <div class="video-controls"></div>
    <button id="fullscreen-toggle"></button>
  </div>
  <button id="play-pause"></button>
  <input id="seek-bar" />
`;

Object.defineProperty(window.HTMLMediaElement.prototype, "play", {
  configurable: true,
  value: jest.fn(() => Promise.resolve()),
});

let setup;

beforeAll(async () => {
  const mod = await import("../../app/static/js/video.js");
  setup = mod.setupVideoControls;
});

jest.useFakeTimers();

test("fullscreen button fades after idle", () => {
  setup();
  jest.advanceTimersByTime(3000);
  const btn = document.getElementById("fullscreen-toggle");
  expect(btn.classList.contains("fade-out")).toBe(true);
  btn.classList.remove("fade-out");
  const container = document.querySelector(".video-container");
  container.dispatchEvent(new Event("mousemove"));
  expect(btn.classList.contains("fade-out")).toBe(false);
});
