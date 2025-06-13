import { jest } from "@jest/globals";

document.body.innerHTML = `
  <div class="video-container">
    <div class="loading-spinner"></div>
    <video preload="none" data-hd-src="/clip/cam1">
      <source src="/last_video/cam1" type="video/mp4" />
    </video>
  </div>
`;

let enqueueClip;

beforeAll(async () => {
  const mod = await import("../../app/static/js/video.js");
  enqueueClip = mod.enqueueClip;
});

jest.useFakeTimers();

test("backoff queue when clip load fails", () => {
  const video = document.querySelector("video");
  video.load = jest.fn(() => {
    video.dispatchEvent(new Event("error"));
  });
  const orig = global.setTimeout;
  global.setTimeout = jest.fn();
  enqueueClip(video);
  expect(setTimeout).toHaveBeenLastCalledWith(expect.any(Function), 2000);
  global.setTimeout = orig;
});
