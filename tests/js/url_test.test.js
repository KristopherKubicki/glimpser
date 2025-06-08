import { jest } from "@jest/globals";

document.body.innerHTML = `<input id="url"><span id="url-status"></span>`;

let initUrlTester;

beforeAll(async () => {
  ({ initUrlTester } = await import("../../app/static/js/url_test.js"));
});

describe("url_test", () => {
  test("shows status after fetch", async () => {
    global.fetch = jest.fn(() =>
      Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ ok: true }),
      }),
    );
    initUrlTester();
    document.dispatchEvent(new Event("DOMContentLoaded"));
    const input = document.getElementById("url");
    input.value = "http://example.com";
    input.dispatchEvent(new Event("change"));
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(fetch).toHaveBeenCalled();
    const status = document.getElementById("url-status");
    expect(status.textContent).toBe("✓");
    expect(status.classList.contains("ok")).toBe(true);
  });
});
