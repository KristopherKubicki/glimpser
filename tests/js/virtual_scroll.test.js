import { jest } from "@jest/globals";

document.body.innerHTML = `<div id="list"></div>`;

let virtualizeElements;

beforeAll(async () => {
  const mod = await import("../../app/static/js/templates.js");
  virtualizeElements = mod.virtualizeElements;
});

test("appends next batch when sentinel is visible", () => {
  let ioCallback;
  window.IntersectionObserver = class {
    constructor(cb) {
      ioCallback = cb;
    }
    observe() {}
    unobserve() {}
    disconnect() {}
  };

  const container = document.getElementById("list");
  const elems = Array.from({ length: 4 }, (_, i) => {
    const el = document.createElement("div");
    el.textContent = `item${i}`;
    return el;
  });

  virtualizeElements(container, elems, 2);

  expect(container.children.length).toBe(3); // 2 items + sentinel
  const sentinel = container.lastElementChild;
  ioCallback([{ target: sentinel, isIntersecting: true }]);
  expect(container.children.length).toBe(4); // sentinel removed after final batch
});
