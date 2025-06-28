import { jest } from "@jest/globals";

jest.unstable_mockModule("../../app/static/js/login.js", () => ({
  attemptAutoLogin: jest.fn(),
}));

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

let handleNetworkOffline;
let handleNetworkOnline;
let attemptAutoLogin;

beforeAll(async () => {
  const mod = await import("../../app/static/js/live.js");
  handleNetworkOffline = mod.handleNetworkOffline;
  handleNetworkOnline = mod.handleNetworkOnline;
  const loginMod = await import("../../app/static/js/login.js");
  attemptAutoLogin = loginMod.attemptAutoLogin;
});

global.fetch = jest.fn(() =>
  Promise.resolve({ ok: true, redirected: false, json: () => Promise.resolve({ online: true }) }),
);

beforeEach(() => {
  jest.clearAllMocks();
  document.getElementById("offline-indicator").style.display = "none";
  document.getElementById("offline-message").textContent = "";
});

test("shows offline overlay and resumes when back online", async () => {
  const video = document.getElementById("live-video");
  video.currentTime = 5;
  handleNetworkOffline();
  expect(document.getElementById("offline-indicator").style.display).toBe(
    "block",
  );
  expect(document.getElementById("offline-message").textContent).toBe(
    "Offline. Reconnecting...",
  );
  await handleNetworkOnline();
  expect(fetch).toHaveBeenCalledWith("/network_status");
  expect(document.getElementById("offline-indicator").style.display).toBe(
    "none",
  );
});

test("auto login attempts when network_status redirects", async () => {
  attemptAutoLogin.mockResolvedValue(true);
  global.fetch
    .mockResolvedValueOnce({ ok: false, redirected: true, json: () => Promise.resolve({}) })
    .mockResolvedValueOnce({ ok: true, redirected: false, json: () => Promise.resolve({ online: true }) });
  handleNetworkOffline();
  await handleNetworkOnline();
  expect(attemptAutoLogin).toHaveBeenCalled();
  expect(fetch).toHaveBeenCalledTimes(2);
  expect(document.getElementById("offline-indicator").style.display).toBe(
    "none",
  );
});
