import { jest } from "@jest/globals";

document.body.innerHTML = `<span id="item" title="Hello"></span>`;

let initTooltips;

beforeAll(async () => {
  const mod = await import("../../app/static/js/tooltips.js");
  initTooltips = mod.initTooltips;
});

beforeEach(() => {
  jest.clearAllMocks();
  document.querySelector("#item").setAttribute("title", "Hello");
});

test("repositions tooltip above when near bottom", () => {
  Object.defineProperty(window, "innerWidth", { configurable: true, writable: true, value: 300 });
  Object.defineProperty(window, "innerHeight", { configurable: true, writable: true, value: 500 });
  Object.defineProperty(window, "scrollY", { configurable: true, writable: true, value: 0 });

  initTooltips();
  document.dispatchEvent(new Event("DOMContentLoaded"));

  const tooltip = document.querySelector(".dynamic-tooltip");
  Object.defineProperty(tooltip, "offsetWidth", { configurable: true, value: 50 });
  Object.defineProperty(tooltip, "offsetHeight", { configurable: true, value: 40 });

  const el = document.getElementById("item");
  el.dispatchEvent(
    new MouseEvent("mouseover", { clientX: 260, clientY: 490, bubbles: true })
  );

  expect(tooltip.style.top).toBe("440px");
});
