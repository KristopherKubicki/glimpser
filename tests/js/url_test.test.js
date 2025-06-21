import { jest } from "@jest/globals";

const formHtml =
  '<form><input id="url" data-default-url="http://example.com/test"><span id="url-status"></span><img id="url-preview"><input type="submit"></form>';

beforeEach(() => {
  document.body.innerHTML = formHtml;
  jest.useFakeTimers();
});

afterEach(() => {
  jest.runOnlyPendingTimers();
  jest.useRealTimers();
});

let initUrlTester;

beforeAll(async () => {
  ({ initUrlTester } = await import("../../app/static/js/url_test.js"));
});

describe("url_test", () => {
  test("shows status after fetch", async () => {
    const res = Promise.resolve({
      ok: true,
      json: () => Promise.resolve({ ok: true }),
    });
    global.fetch = jest.fn(() => res);
    initUrlTester();
    document.dispatchEvent(new Event("DOMContentLoaded"));
    jest.clearAllTimers();
    const input = document.getElementById("url");
    input.value = "http://example.com";
    input.dispatchEvent(new Event("input"));
    jest.advanceTimersByTime(500);
    await Promise.resolve();
    jest.runAllTimers();
    await Promise.resolve();
    await Promise.resolve();
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
    jest.clearAllTimers();
    const input = document.getElementById("url");
    const submit = document.querySelector("input[type='submit']");
    input.value = "http://example.com";
    input.dispatchEvent(new Event("paste"));
    jest.runAllTimers();
    await Promise.resolve();
    await Promise.resolve();
    expect(fetch).toHaveBeenCalled();
    expect(submit.disabled).toBe(false);
  });

  test("auto populates default url", async () => {
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

  test("shows tooltip on error", async () => {
    const res = Promise.resolve({
      ok: true,
      json: () => Promise.resolve({ ok: false, status: 404 }),
    });
    global.fetch = jest.fn(() => res);
    initUrlTester();
    document.dispatchEvent(new Event("DOMContentLoaded"));
    jest.clearAllTimers();
    const input = document.getElementById("url");
    const status = document.getElementById("url-status");
    input.value = "http://bad";
    input.dispatchEvent(new Event("input"));
    jest.advanceTimersByTime(500);
    await Promise.resolve();
    jest.runAllTimers();
    await Promise.resolve();
    await Promise.resolve();
    expect(status.classList.contains("bad")).toBe(true);
    expect(status.title).toBe("HTTP 404");
  });

  test("initializes multiple forms", async () => {
    const multiHtml = `
      <div class="edit-template-container">
        <img id="p1">
        <form><input id="url" data-default-url="http://a"><span id="url-status"></span><input type="submit"></form>
      </div>
      <div class="edit-template-container">
        <img id="p2">
        <form><input id="url" data-default-url="http://b"><span id="url-status"></span><input type="submit"></form>
      </div>`;
    document.body.innerHTML = multiHtml;
    const res = Promise.resolve({
      ok: true,
      json: () => Promise.resolve({ ok: true }),
    });
    global.fetch = jest.fn(() => res);
    initUrlTester();
    document.dispatchEvent(new Event("DOMContentLoaded"));
    jest.advanceTimersByTime(1000);
    await Promise.resolve();
    expect(fetch).toHaveBeenCalledTimes(2);
    const previews = document.querySelectorAll("img");
    previews[1]
      .closest(".edit-template-container")
      .querySelector("#url").value = "http://cam";
    previews[1]
      .closest(".edit-template-container")
      .querySelector("#url")
      .dispatchEvent(new Event("input"));
    jest.advanceTimersByTime(500);
    await Promise.resolve();
    expect(previews[1].src).toContain("http://cam");
  });
});
