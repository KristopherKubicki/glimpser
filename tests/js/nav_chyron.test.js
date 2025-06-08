import { jest } from "@jest/globals";

document.body.innerHTML = `
  <a id="captions"></a>
  <div id="caption-chyron" data-speed="240"></div>
  <nav></nav>
`;

let initNav;

beforeAll(async () => {
  global.fetch = jest.fn(() =>
    Promise.resolve({
      ok: true,
      headers: { get: () => "application/json" },
      json: () =>
        Promise.resolve({ caption: "Hello", timestamp: "2024-01-01 00:00:00" }),
    }),
  );
  global.setInterval = jest.fn();
  const mod = await import("../../app/static/js/nav.js");
  initNav = mod.initNav;
});

describe("caption hover", () => {
  beforeEach(async () => {
    jest.clearAllMocks();
    initNav();
    document.dispatchEvent(new Event("DOMContentLoaded"));
    await Promise.resolve();
  });

  test("sets caption dataset", () => {
    const icon = document.getElementById("captions");
    expect(icon.dataset.caption).toBe("Hello");
    expect(icon.title).toBe("");
  });

  test("mouse enter shows chyron", () => {
    const icon = document.getElementById("captions");
    const chyron = document.getElementById("caption-chyron");
    icon.dispatchEvent(new Event("mouseenter"));
    expect(chyron.classList.contains("show")).toBe(true);
  });

  test("mouse leave hides chyron", () => {
    const icon = document.getElementById("captions");
    const chyron = document.getElementById("caption-chyron");
    icon.dispatchEvent(new Event("mouseenter"));
    icon.dispatchEvent(new Event("mouseleave"));
    expect(chyron.classList.contains("show")).toBe(false);
  });
});
