import { jest } from "@jest/globals";
import {
  livePilotEligible,
  mountKioskLive,
} from "../../app/static/js/kiosk_live.js";
let scene, video, time, ready;
beforeEach(() => {
  jest.useFakeTimers();
  jest.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue();
  jest.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => {});
  jest.spyOn(HTMLMediaElement.prototype, "load").mockImplementation(() => {});
  document.body.innerHTML =
    '<section data-hero-name="ExampleApproach"><div class="landing-hero-media"></div><div data-source-freshness="{}"></div></section>';
  const config = document.createElement("script");
  config.id = "kiosk-live-settings";
  config.type = "application/json";
  config.textContent = JSON.stringify({
    ExampleApproach: { provider: "stream", profile: "main", quality: "kiosk" },
    ExampleDoor: {
      provider: "stream",
      profile: "main",
      quality: "auto",
      source_fps: 1,
    },
  });
  document.body.append(config);
  scene = document.querySelector("section");
  time = 0;
  ready = jest.fn();
});
afterEach(() => {
  jest.clearAllTimers();
  jest.useRealTimers();
  jest.restoreAllMocks();
});
function mount() {
  let handle = mountKioskLive(scene, { onReady: ready });
  video = scene.querySelector("video");
  Object.defineProperty(video, "currentTime", {
    get: () => time,
    configurable: true,
  });
  Object.defineProperty(video, "videoWidth", { get: () => 480 });
  return handle;
}
test("only verified cameras in office and living are eligible", () => {
  expect(livePilotEligible(scene, "office")).toBe(true);
  expect(livePilotEligible(scene, "living")).toBe(true);
  expect(livePilotEligible(scene, "public")).toBe(false);
  expect(livePilotEligible(scene, "hal")).toBe(false);
  scene.dataset.heroName = "UnverifiedCamera";
  expect(livePilotEligible(scene, "living")).toBe(false);
  expect(livePilotEligible(scene, "office")).toBe(false);
});
test("unavailable and overdue captures are vetoed", () => {
  scene.dataset.landingFeedUnavailable = "true";
  expect(livePilotEligible(scene, "office")).toBe(false);
  delete scene.dataset.landingFeedUnavailable;
  scene.querySelector("[data-source-freshness]").dataset.sourceFreshness =
    '{"capture_overdue":true}';
  expect(livePilotEligible(scene, "office")).toBe(false);
});
test("requires advancing video before declaring LIVE", () => {
  const handle = mount();
  jest.advanceTimersByTime(1000);
  expect(ready).not.toHaveBeenCalled();
  time = 1;
  jest.advanceTimersByTime(1000);
  expect(ready).toHaveBeenCalledTimes(1);
  expect(scene.classList.contains("has-kiosk-live")).toBe(true);
  handle.dispose();
});
test("startup timeout keeps saved capture and closes connection", () => {
  mount();
  jest.advanceTimersByTime(21000);
  expect(scene.querySelector("video")).toBeNull();
  expect(scene.textContent).toContain("SAVED");
  expect(ready).not.toHaveBeenCalled();
});
test("stall restores saved capture without advancing the rotation", () => {
  mount();
  time = 1;
  jest.advanceTimersByTime(1000);
  jest.advanceTimersByTime(6000);
  expect(scene.querySelector("video")).toBeNull();
  expect(scene.classList.contains("has-kiosk-live")).toBe(false);
  expect(scene.textContent).toContain("SAVED");
  expect(ready).toHaveBeenCalledTimes(1);
});
test("dispose releases video and prevents late error UI", () => {
  const handle = mount();
  handle.dispose();
  video.dispatchEvent(new Event("error"));
  jest.advanceTimersByTime(15000);
  expect(scene.querySelector(".kiosk-live-note")).toBeNull();
  expect(video.hasAttribute("src")).toBe(false);
  expect(ready).not.toHaveBeenCalled();
});

test("front door uses verified main path and honest source rate", () => {
  scene.dataset.heroName = "ExampleDoor";
  expect(livePilotEligible(scene, "office")).toBe(true);
  const handle = mount();
  expect(video.getAttribute("src")).toContain("profile=main&quality=auto");
  expect(scene.querySelector(".kiosk-live-label").textContent).toContain(
    "1 fps source",
  );
  handle.dispose();
});

test("advancing media time cannot conceal frozen video frames", () => {
  mount();
  let frames = 1;
  video.getVideoPlaybackQuality = () => ({
    totalVideoFrames: frames,
    droppedVideoFrames: 0,
  });
  time = 1;
  jest.advanceTimersByTime(1000);
  expect(scene.classList.contains("has-kiosk-live")).toBe(true);
  for (let i = 0; i < 6; i++) {
    time += 1;
    jest.advanceTimersByTime(1000);
  }
  expect(scene.querySelector("video")).toBeNull();
  expect(scene.textContent).toContain("SAVED");
});

test("dropped frames alone do not declare a live picture", () => {
  const handle = mount();
  time = 5;
  video.getVideoPlaybackQuality = () => ({
    totalVideoFrames: 10,
    droppedVideoFrames: 10,
  });
  jest.advanceTimersByTime(1000);
  expect(ready).not.toHaveBeenCalled();
  handle.dispose();
});

test.each(["{}", "invalid", '{"ExampleApproach":{"provider":"unknown"}}'])(
  "missing or invalid settings do not start a stream: %s",
  (settings) => {
    document.getElementById("kiosk-live-settings").textContent = settings;
    expect(livePilotEligible(scene, "office")).toBe(false);
    mountKioskLive(scene).dispose();
    expect(scene.querySelector("video")).toBeNull();
  },
);
test("configured labels render as text", () => {
  document.getElementById("kiosk-live-settings").textContent = JSON.stringify({
    ExampleApproach: { provider: "stream", label: "<img src=x>" },
  });
  const handle = mount();
  expect(scene.querySelector(".kiosk-live-label").textContent).toContain(
    "<img src=x>",
  );
  expect(scene.querySelector("img")).toBeNull();
  handle.dispose();
});
