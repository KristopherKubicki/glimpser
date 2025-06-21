import { jest } from "@jest/globals";

const html = `
  <div id="settings-search" class="hidden">
    <input id="search-input" />
  </div>
  <table class="settings-table">
    <thead>
      <tr><th class="searchable">Name</th><th class="searchable">Value</th></tr>
    </thead>
    <tbody>
      <tr><td>Alpha</td><td>Beta</td></tr>
      <tr><td>Gamma</td><td>Delta</td></tr>
    </tbody>
  </table>
`;

document.body.innerHTML = html;

let initSettingsSearch;

beforeAll(async () => {
  const mod = await import("../../app/static/js/settings.js");
  initSettingsSearch = mod.initSettingsSearch;
});

beforeEach(() => {
  document.body.innerHTML = html;
});

test("clicking header shows search input", () => {
  initSettingsSearch();
  document.dispatchEvent(new Event("DOMContentLoaded"));

  const header = document.querySelectorAll(".settings-table th.searchable")[1];
  const container = document.getElementById("settings-search");
  const input = document.getElementById("search-input");
  input.value = "foo";

  header.click();

  expect(container.classList.contains("hidden")).toBe(false);
  expect(document.activeElement).toBe(input);
  expect(input.value).toBe("");
});

test("filtering hides non matching rows", () => {
  initSettingsSearch();
  document.dispatchEvent(new Event("DOMContentLoaded"));

  const header = document.querySelector(".settings-table th.searchable");
  header.click();

  const input = document.getElementById("search-input");
  const rows = document.querySelectorAll(".settings-table tbody tr");

  input.value = "gam";
  input.dispatchEvent(new Event("input"));

  expect(rows[0].style.display).toBe("none");
  expect(rows[1].style.display).toBe("");
});
