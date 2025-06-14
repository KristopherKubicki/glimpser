import { jest } from "@jest/globals";

const formHtml =
  '<form><input id="url" data-default-url="http://example.com/test"><span id="url-status"></span><img id="url-preview"><input type="submit"></form>';

beforeEach(() => {
  document.body.innerHTML = formHtml;
});

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
    await Promise.resolve();
    await Promise.resolve();
    fetch.mockClear();
    global.fetch.mockImplementation(() =>
      Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ ok: true }),
      }),
    );
    const input = document.getElementById("url");
    input.value = "http://example.com";
    input.dispatchEvent(new Event("change"));
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(fetch).toHaveBeenCalledTimes(2);
    const status = document.getElementById("url-status");
    expect(status.textContent).toBe("");
    expect(status.classList.contains("ok")).toBe(true);
    const preview = document.getElementById("url-preview");
    expect(preview.src).toContain("http://example.com");
  });

  test("paste triggers check and enables submit", async () => {
    const res = Promise.resolve({
      ok: true,
      json: () => Promise.resolve({ ok: true }),
    });
    global.fetch = jest.fn(() => res);
    initUrlTester();
    document.dispatchEvent(new Event("DOMContentLoaded"));
    const input = document.getElementById("url");
    const submit = document.querySelector("input[type='submit']");
    input.value = "http://example.com";
    input.dispatchEvent(new Event("paste"));
    await new Promise((r) => setTimeout(r, 0));
    expect(fetch).toHaveBeenCalled();
    expect(submit.disabled).toBe(false);
  });

  test("auto populates default url", async () => {
    jest.useFakeTimers();
    const res = Promise.resolve({
      ok: true,
      json: () => Promise.resolve({ ok: true }),
    });
    global.fetch = jest.fn(() => res);
    initUrlTester();
    document.dispatchEvent(new Event("DOMContentLoaded"));
    jest.advanceTimersByTime(1000);
    await Promise.resolve();
    const input = document.getElementById("url");
    expect(input.value).toBe("http://example.com/test");
    expect(fetch).toHaveBeenCalled();
  });
});
