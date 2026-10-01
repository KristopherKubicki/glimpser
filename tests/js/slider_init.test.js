import { jest } from "@jest/globals";

// tests/js/slider_init.test.js

document.body.innerHTML = `
  <header></header>
  <div id="network-banner" class="network-banner"></div>
  <div id="template-list" style="gap:0"></div>
  <div id="camera-table"></div>
  <input id="grid-width-slider" type="range" value="360">
  <footer></footer>
`;

let initTemplates;

beforeAll(async () => {
  const mod = await import("../../app/static/js/templates.js");
  initTemplates = mod.initTemplates;
});

describe("slider initialization", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    localStorage.setItem("gridAutofit", "1");
    const list = document.getElementById("template-list");
    list.innerHTML = "";
    list.style.gap = "0px";
    Object.defineProperty(document.querySelector("header"), "offsetHeight", {
      configurable: true,
      value: 40,
    });
    Object.defineProperty(
      document.getElementById("network-banner"),
      "offsetHeight",
      {
        configurable: true,
        value: 10,
      },
    );
    document.documentElement.style.setProperty("--footer-space", "50px");
  });

  test.each([
    [1920, 1080, 4, 871],
    [1920, 1080, 2, 960],
    [1280, 720, 4, 551],
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
      // The real app sizes the grid to the template-list viewport (not full window).
      // Simulate that in jsdom so the auto-fit math is realistic.
      const headerH = document.querySelector("header")?.offsetHeight || 0;
      const bannerH = document.getElementById("network-banner")?.offsetHeight || 0;
      const footerSpace = parseFloat(
        getComputedStyle(document.documentElement).getPropertyValue("--footer-space") ||
          "0",
      );
      list.getBoundingClientRect = () => ({
        x: 0,
        y: headerH + bannerH,
        top: headerH + bannerH,
        left: 0,
        width: window.innerWidth,
        height: Math.max(0, window.innerHeight - headerH - bannerH - footerSpace),
        right: window.innerWidth,
        bottom: window.innerHeight - footerSpace,
        toJSON: () => ({}),
      });
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
