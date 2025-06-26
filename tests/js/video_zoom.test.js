import { jest } from "@jest/globals";

document.body.innerHTML = `
  <div class="video-container">
    <video id="live-video"></video>
  </div>
  <div class="edit-template-preview">
    <img id="url-preview" />
  </div>
`;

let init;

beforeAll(async () => {
  ({ initVideoZoom: init } = await import("../../app/static/js/zoom.js"));
});

jest.useFakeTimers();

test("zooms on wheel and resets on mouse leave", () => {
  const video = document.getElementById("live-video");
  video.getBoundingClientRect = () => ({
    left: 0,
    top: 0,
    width: 100,
    height: 100,
  });
  init();
  document.dispatchEvent(new Event("DOMContentLoaded"));
  const wheel = new WheelEvent("wheel", {
    deltaY: -100,
    clientX: 50,
    clientY: 50,
  });
  video.dispatchEvent(wheel);
  expect(video.style.transform).toMatch(/scale/);
  video.dispatchEvent(new Event("mouseleave"));
  jest.advanceTimersByTime(1000);
  expect(video.style.transform).toBe("");
});

test("zooms preview on wheel", () => {
  const img = document.getElementById("url-preview");
  img.getBoundingClientRect = () => ({
    left: 0,
    top: 0,
    width: 100,
    height: 100,
  });
  init();
  document.dispatchEvent(new Event("DOMContentLoaded"));
  const wheel = new WheelEvent("wheel", {
    deltaY: -100,
    clientX: 50,
    clientY: 50,
  });
  img.dispatchEvent(wheel);
  expect(img.style.transform).toMatch(/scale/);
  img.dispatchEvent(new Event("mouseleave"));
  jest.advanceTimersByTime(1000);
  expect(img.style.transform).toBe("");
});
