import { jest } from "@jest/globals";

document.body.innerHTML = `
  <div class="thumbnail-video">
    <img class="thumbnail" src="#" />
    <video class="hover-video" preload="none">
      <source src="/last_video/cam1" type="video/mp4" />
    </video>
  </div>
`;

let setup;

beforeAll(async () => {
  const mod = await import("../../app/static/js/video.js");
  setup = mod.setupStatusPageVideoHover;
});

test("scrub tooltip appears on hover", () => {
  Object.defineProperty(HTMLMediaElement.prototype, "duration", {
    configurable: true,
    get() {
      return 10;
    },
  });
  setup();
  const cell = document.querySelector(".thumbnail-video");
  cell.dispatchEvent(new MouseEvent("mouseenter", { clientX: 5, clientY: 5 }));
  cell.dispatchEvent(new MouseEvent("mousemove", { clientX: 5, clientY: 5 }));
  const tooltip = document.querySelector(".scrub-tooltip");
  expect(tooltip).not.toBeNull();
  expect(tooltip.classList.contains("visible")).toBe(true);
});
