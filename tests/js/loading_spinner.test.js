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
let showBounce;

beforeAll(async () => {
  const mod = await import("../../app/static/js/video.js");
  enqueueClip = mod.enqueueClip;
  showBounce = mod.showBounce;
});

jest.useFakeTimers();

test("spinner visible while clip loads", () => {
  const video = document.querySelector("video");
  const spinner = document.querySelector(".loading-spinner");
  video.load = jest.fn(() => {
    setTimeout(() => video.dispatchEvent(new Event("canplay")), 0);
  });
  enqueueClip(video);
  expect(spinner.classList.contains("visible")).toBe(true);
  jest.runAllTimers();
  expect(spinner.classList.contains("visible")).toBe(false);
});

test("spinner bounces when clip fails", () => {
  const video = document.querySelector("video");
  const spinner = document.querySelector(".loading-spinner");
  showBounce(video);
  expect(spinner.classList.contains("bounce")).toBe(true);
});
