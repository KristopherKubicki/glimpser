import { jest } from "@jest/globals";

function setupDom() {
  document.body.innerHTML = `
    <div id="videos-modal" class="modal">
      <video data-file="clip1.mp4"></video>
      <video data-file="last_video.mp4"></video>
    </div>
    <video id="live-video"><source /></video>
    <button id="prev-clip-btn"></button>
    <button id="next-clip-btn"></button>
  `;
}

setupDom();

let init;

beforeAll(async () => {
  const mod = await import("../../app/static/js/recent_videos.js");
  init = mod.initRecentVideosModal;
});

beforeEach(() => {
  setupDom();
});

test("clicking a modal video loads clip and closes modal", () => {
  window.closeGenericModal = jest.fn();
  init(["clip1.mp4", "last_video.mp4"], "cam1");
  const clip = document.querySelector('video[data-file="clip1.mp4"]');
  clip.dispatchEvent(new Event("click"));
  const src = document.querySelector("#live-video source").src;
  expect(src).toMatch(/\/videos\/cam1\/clip1.mp4$/);
  expect(window.closeGenericModal).toHaveBeenCalledWith("videos-modal");
});

test("initial clip is most recent with live button enabled", () => {
  init(["clip1.mp4", "clip2.mp4", "last_video.mp4"], "cam1");
  const prev = document.getElementById("prev-clip-btn");
  const next = document.getElementById("next-clip-btn");
  expect(prev.disabled).toBe(false);
  expect(next.textContent).toBe("Live");
});
