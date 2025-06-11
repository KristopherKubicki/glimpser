import { jest } from "@jest/globals";

document.body.innerHTML = `
  <div class="video-container">
    <video id="live-video"></video>
    <div class="video-controls"></div>
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

test("controls fade and autoplay after idle", () => {
  setup();
  const container = document.querySelector(".video-container");
  container.dispatchEvent(new Event("mousemove"));
  jest.advanceTimersByTime(3000);
  const controls = document.querySelector(".video-controls");
  expect(controls.classList.contains("fade-out")).toBe(true);
  jest.advanceTimersByTime(57000);
  const video = document.getElementById("live-video");
  expect(video.play).toHaveBeenCalled();
  expect(video.playbackRate).toBe(0.5);
});
