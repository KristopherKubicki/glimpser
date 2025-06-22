import { jest } from "@jest/globals";

document.body.innerHTML = `
  <div class="thumbnail-video">
    <img class="thumbnail" src="#" />
    <video class="hover-video" preload="none" data-hd-src="/clip/cam1">
      <source src="/last_video/cam1" type="video/mp4" />
    </video>
  </div>
`;

let setup;

beforeAll(async () => {
  const mod = await import("../../app/static/js/video.js");
  setup = mod.setupStatusPageVideoHover;
});

test("switches to clip when video becomes visible", () => {
  let cb;
  window.IntersectionObserver = class {
    constructor(fn) {
      cb = fn;
    }
    observe() {}
    unobserve() {}
    disconnect() {}
  };

  setup();
  const video = document.querySelector("video");
  const source = video.querySelector("source");
  expect(source.src).toMatch(/\/last_video\/cam1$/);

  cb([{ target: video, isIntersecting: true }]);

  expect(source.src).toMatch(/\/clip\/cam1$/);
});
