import { jest } from "@jest/globals";

let initCliHelp;

beforeAll(async () => {
  const mod = await import("../../app/static/js/cli_help.js");
  initCliHelp = mod.initCliHelp;
});

beforeEach(() => {
  document.body.innerHTML = `
    <button id="load-cli-help"></button>
    <pre id="cli-help" class="hidden"></pre>
  `;
  global.fetch = jest.fn();
  jest.clearAllMocks();
});

test("loads help text and disables button", async () => {
  global.fetch.mockResolvedValueOnce({
    text: () => Promise.resolve("help text"),
  });
  initCliHelp();
  document.dispatchEvent(new Event("DOMContentLoaded"));
  document.getElementById("load-cli-help").click();
  await Promise.resolve();
  await Promise.resolve();
  expect(fetch).toHaveBeenCalledWith("/cli_help");
  const output = document.getElementById("cli-help");
  expect(output.textContent).toBe("help text");
  expect(output.classList.contains("hidden")).toBe(false);
  expect(document.getElementById("load-cli-help").disabled).toBe(true);
});

test("shows error text when fetch fails", async () => {
  global.fetch.mockRejectedValueOnce(new Error("fail"));
  initCliHelp();
  document.dispatchEvent(new Event("DOMContentLoaded"));
  document.getElementById("load-cli-help").click();
  await Promise.resolve();
  await Promise.resolve();
  const output = document.getElementById("cli-help");
  expect(output.textContent).toBe("Failed to load help.");
  expect(output.classList.contains("hidden")).toBe(false);
  expect(document.getElementById("load-cli-help").disabled).toBe(true);
});
