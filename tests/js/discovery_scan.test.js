import { jest } from "@jest/globals";

let initDiscoveryScan;

beforeAll(async () => {
  const mod = await import("../../app/static/js/discovery_scan.js");
  initDiscoveryScan = mod.initDiscoveryScan;
});

beforeEach(() => {
  document.body.innerHTML = `
    <div class="discovery-page" data-existing-map="{}" data-icon-url="/icons.svg">
      <input id="cidr-input" />
      <button id="discover-btn"></button>
      <span id="discover-message"></span>
      <progress id="discover-progress"></progress>
      <table><tbody id="discover-body"></tbody></table>
      <button id="export-json"></button>
      <button id="export-csv"></button>
    </div>`;
  global.EventSource = jest.fn(() => ({
    onmessage: null,
    onerror: null,
    close: jest.fn(),
  }));
  global.fetch = jest.fn(() =>
    Promise.resolve({ json: () => Promise.resolve({ status: "ready" }) }),
  );
});

afterEach(() => {
  jest.clearAllMocks();
});

test("starts scan on click", async () => {
  initDiscoveryScan();
  document.dispatchEvent(new Event("DOMContentLoaded"));
  document.getElementById("discover-btn").click();
  await Promise.resolve();
  await Promise.resolve();
  await Promise.resolve();
  expect(EventSource).toHaveBeenCalledWith("/discover/scan_stream");
});

test("enables export after results arrive", async () => {
  initDiscoveryScan();
  document.dispatchEvent(new Event("DOMContentLoaded"));
  document.getElementById("discover-btn").click();
  await Promise.resolve();
  await Promise.resolve();
  await Promise.resolve();
  await Promise.resolve();
  const es = EventSource.mock.results[0].value;
  es.onmessage({ data: JSON.stringify({ cameras: [{ ip: "1" }] }) });
  const exportJson = document.getElementById("export-json");
  expect(exportJson.disabled).toBe(false);
});
