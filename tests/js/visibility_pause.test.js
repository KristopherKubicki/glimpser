import { jest } from "@jest/globals";

Object.defineProperty(window.HTMLMediaElement.prototype, "pause", {
  configurable: true,
  value: jest.fn(),
});

document.body.innerHTML = `
  <video data-hd-src="/clip/cam1"><source src="/last_video/cam1" /></video>
  <video data-hd-src="/clip/cam2"><source src="/last_video/cam2" /></video>
`;

let enqueueClip, initVisibilityHandler;

beforeAll(async () => {
  const mod = await import("../../app/static/js/video.js");
  enqueueClip = mod.enqueueClip;
  initVisibilityHandler = mod.initVisibilityHandler;
});

jest.useFakeTimers();

test("pauses videos and clears queue on tab hide", () => {
  const vids = document.querySelectorAll("video");
  vids.forEach((v) => (v.load = jest.fn()));
  initVisibilityHandler();
  enqueueClip(vids[0]);
  enqueueClip(vids[1]);
  Object.defineProperty(document, "hidden", { value: true, configurable: true });
  document.dispatchEvent(new Event("visibilitychange"));
  vids.forEach((v) => expect(v.pause).toHaveBeenCalled());
  jest.runOnlyPendingTimers();
});
