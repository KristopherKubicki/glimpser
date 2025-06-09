import { jest } from "@jest/globals";

let initTabs;

beforeAll(async () => {
  const mod = await import("../../app/static/js/tabs.js");
  initTabs = mod.initTabs;
});

describe("tabs", () => {
  beforeEach(() => {
    document.body.innerHTML = `
      <button class="tab-link" data-tab="one"></button>
      <button class="tab-link" data-tab="two"></button>
      <div id="one" class="tab-content"></div>
      <div id="two" class="tab-content"></div>
    `;
    Object.defineProperty(window, "location", {
      writable: true,
      configurable: true,
      value: { pathname: "/foo", search: "" },
    });
    localStorage.clear();
  });

  test("click stores tab", () => {
    initTabs();
    document.dispatchEvent(new Event("DOMContentLoaded"));
    document.querySelector('[data-tab="two"]').click();
    expect(localStorage.getItem("lastTab:/foo")).toBe("two");
  });

  test("stored tab activates on load", () => {
    localStorage.setItem("lastTab:/foo", "two");
    initTabs();
    document.dispatchEvent(new Event("DOMContentLoaded"));
    expect(document.getElementById("two").classList.contains("active")).toBe(
      true,
    );
  });
});
