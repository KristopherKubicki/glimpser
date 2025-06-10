import { jest } from "@jest/globals";

document.body.innerHTML = `
  <div class="video-container"></div>
  <video id="live-video"></video>
  <img id="live-image" />
  <div id="template-details"></div>
  <div id="speed-container"></div>
  <input id="speed-slider" value="0" />
  <span id="speed-value"></span>
  <div id="video-overlay"></div>
  <div id="loading-indicator"></div>
  <div id="play-pause-indicator"></div>
  <div id="offline-indicator"></div>
  <div id="offline-message"></div>
  <div id="capture-error-indicator"></div>
  <div id="capture-error-message"></div>
  <div id="stream-error-indicator"></div>
  <div id="stream-error-message"></div>
  <div id="error-message"></div>
  <button id="play-pause"></button>
  <div id="toggle-details"></div>
  <input id="seek-bar" />
  <div id="jog-shuttle"></div>
  <select id="group-selector"></select>
  <select id="video-source"><option value="mjpg" selected>MJPG</option></select>
`;

Object.defineProperty(window.HTMLMediaElement.prototype, "pause", {
  configurable: true,
  value: jest.fn(),
});
Object.defineProperty(window.HTMLMediaElement.prototype, "play", {
  configurable: true,
  value: jest.fn(() => Promise.resolve()),
});

window.templateDetails = { cam1: {}, cam2: {} };

let setClipSrc;

beforeAll(async () => {
  const mod = await import("../../app/static/js/live.js");
  setClipSrc = mod.setClipSrc;
});

jest.useFakeTimers();

test("falls back to stream when clip throttled", () => {
  const video = document.getElementById("live-video");
  setClipSrc("cam1");
  expect(video.src).toMatch(/\/clip\/cam1$/);
  jest.advanceTimersByTime(1000);
  setClipSrc("cam2");
  expect(video.src).toMatch(/\/stream.mp4\?camera=cam2$/);
  jest.advanceTimersByTime(30000);
  setClipSrc("cam2");
  expect(video.src).toMatch(/\/clip\/cam2$/);
});
