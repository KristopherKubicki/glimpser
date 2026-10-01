import { jest } from "@jest/globals";
import { initNav } from "../../app/static/js/nav.js";

test("live header wakes for keyboard and touch and stays visible during navigation", () => {
  jest.useFakeTimers();
  global.fetch = jest.fn(() =>
    Promise.resolve({
      ok: true,
      headers: { get: () => "application/json" },
      json: () => Promise.resolve([]),
    }),
  );
  document.body.innerHTML = `
    <header><nav><a href="#camera">Camera</a><select><option>All</option></select></nav></header>
    <main class="video-container"><button>Player</button></main>
  `;
  initNav();
  document.dispatchEvent(new Event("DOMContentLoaded"));
  const header = document.querySelector("header");
  const faded = () => header.classList.contains("fade-out");
  try {
    jest.advanceTimersByTime(3000);
    expect(faded()).toBe(true);
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Tab" }));
    expect(faded()).toBe(false);
    document.querySelector("nav a").focus();
    jest.advanceTimersByTime(9000);
    expect(faded()).toBe(false);
    document.querySelector("nav select").focus();
    jest.advanceTimersByTime(9000);
    expect(faded()).toBe(false);
    document.querySelector("main button").focus();
    jest.advanceTimersByTime(3000);
    expect(faded()).toBe(true);
    document.dispatchEvent(new Event("touchstart"));
    expect(faded()).toBe(false);
    jest.advanceTimersByTime(3000);
    expect(faded()).toBe(true);
    const cachedHide = new Event("pagehide");
    Object.defineProperty(cachedHide, "persisted", { value: true });
    window.dispatchEvent(cachedHide);
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Tab" }));
    expect(faded()).toBe(false);
    jest.advanceTimersByTime(3000);
    expect(faded()).toBe(true);
    window.dispatchEvent(new Event("pagehide"));
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Tab" }));
    expect(faded()).toBe(true);
  } finally {
    window.dispatchEvent(new Event("pagehide"));
    jest.clearAllTimers();
    jest.useRealTimers();
  }
});
