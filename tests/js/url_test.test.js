import { jest } from "@jest/globals";

document.body.innerHTML = `<input id="url"><span id="url-status"></span><img id="url-preview">`;

let initUrlTester;

beforeAll(async () => {
  ({ initUrlTester } = await import("../../app/static/js/url_test.js"));
});

describe("url_test", () => {
  test("shows status after fetch", async () => {
    const responses = [
      Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ ok: true }),
      }),
      Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ status: "ok" }),
      }),
    ];
    global.fetch = jest.fn(() => responses.shift());
    initUrlTester();
    document.dispatchEvent(new Event("DOMContentLoaded"));
    const input = document.getElementById("url");
    input.value = "http://example.com";
    input.dispatchEvent(new Event("change"));
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(fetch).toHaveBeenCalledTimes(2);
    const status = document.getElementById("url-status");
    expect(status.textContent).toBe("✓");
    expect(status.classList.contains("ok")).toBe(true);
    const preview = document.getElementById("url-preview");
    expect(preview.src).toContain("http://example.com");
  });
});
