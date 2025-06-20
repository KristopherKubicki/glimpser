import { jest } from "@jest/globals";

document.body.innerHTML = `
  <div id="search-container" class="fade-out"></div>
  <input id="search-input" />
  <input id="other" />
`;

let initSearchShortcut;

beforeAll(async () => {
  const mod = await import("../../app/static/js/search_shortcut.js");
  initSearchShortcut = mod.initSearchShortcut;
});

test("ctrl+f focuses search input", () => {
  initSearchShortcut();
  document.dispatchEvent(new Event("DOMContentLoaded"));
  const input = document.getElementById("search-input");
  const evt = new KeyboardEvent("keydown", { key: "f", ctrlKey: true });
  const prevent = jest.spyOn(evt, "preventDefault");
  document.dispatchEvent(evt);
  expect(prevent).toHaveBeenCalled();
  expect(document.activeElement).toBe(input);
});

test("does not override typing in inputs", () => {
  initSearchShortcut();
  document.dispatchEvent(new Event("DOMContentLoaded"));
  const other = document.getElementById("other");
  other.focus();
  const evt = new KeyboardEvent("keydown", { key: "f", ctrlKey: true });
  const prevent = jest.spyOn(evt, "preventDefault");
  other.dispatchEvent(evt);
  expect(prevent).not.toHaveBeenCalled();
  expect(document.activeElement).toBe(other);
});
