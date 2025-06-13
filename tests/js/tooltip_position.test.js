import { jest } from "@jest/globals";

document.body.innerHTML = `
  <span id="item" title="Hello"></span>
  <div class="video-container" style="position: absolute; top: 0; left: 0; width: 100px; height: 50px;">
    <video id="vid" title="Video tooltip"></video>
  </div>
`;

let initTooltips;
let originalWidth;
let originalHeight;
let originalScrollY;

beforeAll(async () => {
  const mod = await import("../../app/static/js/tooltips.js");
  initTooltips = mod.initTooltips;
});

beforeEach(() => {
  jest.clearAllMocks();
  document.querySelector("#item").setAttribute("title", "Hello");
  originalWidth = window.innerWidth;
  originalHeight = window.innerHeight;
  originalScrollY = window.scrollY;
});

afterEach(() => {
  Object.defineProperty(window, "innerWidth", {
    configurable: true,
    writable: true,
    value: originalWidth,
  });
  Object.defineProperty(window, "innerHeight", {
    configurable: true,
    writable: true,
    value: originalHeight,
  });
  Object.defineProperty(window, "scrollY", {
    configurable: true,
    writable: true,
    value: originalScrollY,
  });
  document
    .querySelectorAll("[data-title]")
    .forEach((el) =>
      el.dispatchEvent(new Event("mouseout", { bubbles: true })),
    );
});

test("repositions tooltip above when near bottom", () => {
  Object.defineProperty(window, "innerWidth", {
    configurable: true,
    writable: true,
    value: 300,
  });
  Object.defineProperty(window, "innerHeight", {
    configurable: true,
    writable: true,
    value: 500,
  });
  Object.defineProperty(window, "scrollY", {
    configurable: true,
    writable: true,
    value: 0,
  });

  initTooltips();
  document.dispatchEvent(new Event("DOMContentLoaded"));

  const tooltip = document.querySelector(".dynamic-tooltip");
  Object.defineProperty(tooltip, "offsetWidth", {
    configurable: true,
    value: 50,
  });
  Object.defineProperty(tooltip, "offsetHeight", {
    configurable: true,
    value: 40,
  });

  const el = document.getElementById("item");
  el.dispatchEvent(
    new MouseEvent("mouseover", { clientX: 260, clientY: 490, bubbles: true }),
  );

  expect(tooltip.style.top).toBe("440px");
});

test("positions tooltip beside video containers", () => {
  Object.defineProperty(window, "innerWidth", {
    configurable: true,
    writable: true,
    value: 300,
  });
  Object.defineProperty(window, "innerHeight", {
    configurable: true,
    writable: true,
    value: 500,
  });

  initTooltips();
  document.dispatchEvent(new Event("DOMContentLoaded"));

  const tooltip = document.querySelector(".dynamic-tooltip");
  Object.defineProperty(tooltip, "offsetWidth", {
    configurable: true,
    value: 50,
  });
  Object.defineProperty(tooltip, "offsetHeight", {
    configurable: true,
    value: 40,
  });

  const vid = document.getElementById("vid");
  const container = document.querySelector(".video-container");
  const rect = { top: 0, left: 0, right: 100, bottom: 50 };
  jest.spyOn(container, "getBoundingClientRect").mockReturnValue(rect);

  vid.dispatchEvent(
    new MouseEvent("mouseover", { clientX: 10, clientY: 10, bubbles: true }),
  );

  expect(parseInt(tooltip.style.left, 10)).toBe(rect.right + 10);
});
