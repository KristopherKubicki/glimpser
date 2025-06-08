import { jest } from "@jest/globals";

// tests/js/slider_init.test.js

document.body.innerHTML = `
  <div id="template-list" style="gap:0"></div>
  <div id="camera-table"></div>
  <input id="grid-width-slider" type="range" value="360">
`;

let initTemplates;

beforeAll(async () => {
  const mod = await import("../../app/static/js/templates.js");
  initTemplates = mod.initTemplates;
});

describe("slider initialization", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    const list = document.getElementById("template-list");
    list.innerHTML = "";
    list.style.gap = "0px";
  });

  test.each([
    [1920, 1080, 4, 960],
    [1920, 1080, 2, 960],
    [1280, 720, 4, 640],
  ])(
    "computes min width %ipx x %ipx with %i cameras",
    (width, height, count, expected) => {
      Object.defineProperty(window, "innerWidth", {
        writable: true,
        configurable: true,
        value: width,
      });
      Object.defineProperty(window, "innerHeight", {
        writable: true,
        configurable: true,
        value: height,
      });

      global.fetch = jest.fn(() => new Promise(() => {}));

      const list = document.getElementById("template-list");
      list.innerHTML = new Array(count)
        .fill('<div class="templateDiv"></div>')
        .join("");

      initTemplates();
      document.dispatchEvent(new Event("DOMContentLoaded"));

      if (window.updateSliderLimits) {
        window.updateSliderLimits();
      }

      const slider = document.getElementById("grid-width-slider");
      expect(slider.min).toBe(expected.toString());
    },
  );
});
