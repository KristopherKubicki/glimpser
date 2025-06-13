import { jest } from "@jest/globals";

document.body.innerHTML = `
  <div class="captions-page">
    <div class="video-container">
      <video class="hover-video" preload="none">
        <source src="/last_video/cam1" type="video/mp4" />
      </video>
    </div>
  </div>
`;

let setup;

beforeAll(async () => {
  const mod = await import("../../app/static/js/video.js");
  setup = mod.setupCaptionsPageVideoHover;
});

test("scrub tooltip is suppressed on captions page hover", () => {
  Object.defineProperty(HTMLMediaElement.prototype, "duration", {
    configurable: true,
    get() {
      return 10;
    },
  });
  setup();
  const container = document.querySelector(".video-container");
  container.dispatchEvent(
    new MouseEvent("mouseenter", { clientX: 5, clientY: 5 }),
  );
  container.dispatchEvent(
    new MouseEvent("mousemove", { clientX: 5, clientY: 5 }),
  );
  const tooltip = document.querySelector(".scrub-tooltip");
  expect(tooltip).toBeNull();
});
