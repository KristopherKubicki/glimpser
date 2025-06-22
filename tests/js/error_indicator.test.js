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

test("shows shake indicator when clip missing", () => {
  const video = document.querySelector("video");
  const spinner = document.querySelector(".loading-spinner");
  video.load = jest.fn(() => {
    video.dispatchEvent(new Event("error"));
  });
  enqueueClip(video);
  expect(spinner.classList.contains("shake")).toBe(true);
  jest.runAllTimers();
  expect(spinner.classList.contains("shake")).toBe(false);
});
