import { jest } from "@jest/globals";

window.__GLIMPSER_DISABLE_BEACONS = true;
document.body.innerHTML = `
  <video id="live-video"><source></source></video>
`;

window.templateDetails = { cam1: {}, cam2: {} };

let init;
let changeGroup;
beforeAll(async () => {
  const mod = await import("../../app/static/js/tile_player.js");
  init = mod.initTilePlayer;
  changeGroup = mod.changeGroup;
});

beforeEach(() => {
  window.localStorage.clear();
});

test("defaults to all cameras", () => {
  init();
  const img = document.getElementById("live-image");
  expect(img.src).toMatch(/\/stream\.mjpg\?group=all&time=\d+$/);
});

test("no clip fetch occurs", async () => {
  global.fetch = jest.fn();
  init();
  await Promise.resolve();
  expect(fetch).not.toHaveBeenCalled();
});

test("group change updates image src", () => {
  jest.useFakeTimers();
  document.body.innerHTML = `
    <video id="live-video"><source></source></video>
    <select id="camera-selector"></select>
  `;

  window.templateDetails = {
    cam1: { groups: "kitchen" },
    cam2: { groups: "kitchen" },
  };

  init();
  changeGroup("kitchen");
  const img = document.getElementById("live-image");
  expect(img.src).toMatch(/\/stream\.mjpg\?group=kitchen&time=\d+$/);
});

test("fallback to nav camera dropdown", () => {
  jest.useFakeTimers();
  document.body.innerHTML = `
    <video id="live-video"><source></source></video>
    <select id="nav-camera-dropdown"></select>
  `;

  window.templateDetails = {
    cam1: { groups: "foo" },
    cam2: { groups: "foo" },
  };

  init();
  changeGroup("foo");
  const img = document.getElementById("live-image");
  expect(img.src).toMatch(/\/stream\.mjpg\?group=foo&time=\d+$/);
});

test("all group uses group mjpeg", () => {
  jest.useFakeTimers();
  document.body.innerHTML = `
    <video id="live-video"><source></source></video>
    <select id="camera-selector"><option>All</option></select>
  `;

  window.templateDetails = { cam1: {}, cam2: {} };

  init();
  changeGroup("all");
  const img = document.getElementById("live-image");
  expect(img.src).toMatch(/\/stream\.mjpg\?group=all&time=\d+$/);
});

test("context menu is suppressed", () => {
  document.body.innerHTML = `
    <video id="live-video"><source></source></video>
  `;

  window.templateDetails = { cam1: {} };

  init();
  const video = document.getElementById("live-video");
  const event = new Event("contextmenu", { bubbles: true, cancelable: true });
  video.dispatchEvent(event);
  expect(event.defaultPrevented).toBe(true);
});

test("clip waits 30s before live", () => {
  jest.useFakeTimers();
  document.body.innerHTML = `
    <video id="live-video"><source src="/last_video/cam1"></source></video>
  `;
  window.templateDetails = { cam1: {} };
  init();
  const img = document.getElementById("live-image");
  expect(img.src).toBe("");
  jest.advanceTimersByTime(29999);
  expect(img.src).toBe("");
  jest.advanceTimersByTime(1);
  expect(img.src).toMatch(/\/stream\.mjpg\?group=all&time=\d+$/);
});

test("init does not duplicate live-image", () => {
  document.body.innerHTML = `
    <video id="live-video"><source></source></video>
  `;
  window.templateDetails = { cam1: {} };
  init();
  expect(document.querySelectorAll("#live-image").length).toBe(1);
  init();
  expect(document.querySelectorAll("#live-image").length).toBe(1);
});

test("fullscreen button requests fullscreen", () => {
  document.body.innerHTML = `
    <div id="container">
      <video id="live-video"><source></source></video>
      <button id="fullscreen-toggle"></button>
    </div>
  `;
  const container = document.getElementById("container");
  container.requestFullscreen = jest.fn();
  window.templateDetails = { cam1: {} };
  init();
  const button = document.getElementById("fullscreen-toggle");
  expect(button.style.display).toBe("block");
  expect(button.getAttribute("aria-label")).toBe("Enter fullscreen");
  button.click();
  expect(container.requestFullscreen).toHaveBeenCalled();
});

test("a rejected fullscreen request can be retried", async () => {
  document.body.innerHTML = `
    <div id="container"><video id="live-video"><source></source></video>
    <button id="fullscreen-toggle"></button></div>`;
  const container = document.getElementById("container");
  container.requestFullscreen = jest
    .fn()
    .mockRejectedValueOnce(new Error("Fullscreen denied"))
    .mockResolvedValueOnce(undefined);
  window.templateDetails = { cam1: {} };
  init();
  const button = document.getElementById("fullscreen-toggle");
  button.click();
  await Promise.resolve();
  expect(button.title).toBe("Could not change fullscreen. Try again.");
  button.click();
  await Promise.resolve();
  expect(container.requestFullscreen).toHaveBeenCalledTimes(2);
  expect(button.title).toBe("Enter fullscreen");
});

test("fullscreen control tracks browser state and prevents duplicate requests", async () => {
  document.body.innerHTML = `<div id="container"><video id="live-video"><source></source></video><button id="fullscreen-toggle"></button></div>`;
  const container = document.getElementById("container");
  let finish;
  container.requestFullscreen = jest.fn(
    () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
  );
  window.templateDetails = { cam1: {} };
  init();
  const button = document.getElementById("fullscreen-toggle");
  try {
    button.click();
    button.click();
    expect(container.requestFullscreen).toHaveBeenCalledTimes(1);
    expect(button.disabled).toBe(true);
    Object.defineProperty(document, "fullscreenElement", {
      configurable: true,
      value: container,
    });
    document.dispatchEvent(new Event("fullscreenchange"));
    expect(button.getAttribute("aria-label")).toBe("Exit fullscreen");
    expect(button.getAttribute("aria-pressed")).toBe("true");
    finish();
    await Promise.resolve();
    expect(button.disabled).toBe(false);
    Object.defineProperty(document, "fullscreenElement", {
      configurable: true,
      value: null,
    });
    document.dispatchEvent(new Event("fullscreenchange"));
    expect(button.getAttribute("aria-label")).toBe("Enter fullscreen");
    expect(button.getAttribute("aria-pressed")).toBe("false");
  } finally {
    Object.defineProperty(document, "fullscreenElement", {
      configurable: true,
      value: null,
    });
    window.dispatchEvent(new Event("pagehide"));
  }
});

test("fullscreen control is hidden when the player cannot request fullscreen", () => {
  document.body.innerHTML = `<div><video id="live-video"><source></source></video><button id="fullscreen-toggle"></button></div>`;
  window.templateDetails = { cam1: {} };
  init();
  expect(document.getElementById("fullscreen-toggle").style.display).toBe(
    "none",
  );
});

test.each([false, true])(
  "live rotator advances using image streams (failed frame: %s)",
  (failedFrame) => {
    jest.useFakeTimers();
    document.body.innerHTML = `
    <video id="live-video"><source></source></video>
  `;
    window.templateDetails = {
      cam1: { url: "rtsp://camera-1.example.test/live" },
      cam2: { url: "rtsp://camera-2.example.test/live" },
    };
    window.history.replaceState({}, "", "/live?rotator=all");
    try {
      init();
      const pending = document.getElementById("live-image-alt");
      expect(pending.src).toMatch(/\/stream\.mjpg\?camera=cam1&time=\d+$/);
      expect(
        document.querySelector("video source").getAttribute("src"),
      ).toBeNull();
      if (failedFrame) pending.dispatchEvent(new Event("error"));
      jest.advanceTimersByTime(failedFrame ? 2000 : 6000);
      expect(pending.src).toMatch(/\/stream\.mjpg\?camera=cam2&time=\d+$/);
    } finally {
      window.dispatchEvent(new Event("pagehide"));
      window.history.replaceState({}, "", "/");
      jest.useRealTimers();
    }
  },
);

test("choosing a camera exits forced rotation and keeps that camera selected", () => {
  jest.useFakeTimers();
  document.body.innerHTML = `
    <video id="live-video"><source></source></video>
    <select id="camera-selector">
      <option value="All">All</option>
      <option value="cam1">cam1</option>
      <option value="cam2">cam2</option>
    </select>
  `;
  window.templateDetails = { cam1: {}, cam2: {} };
  window.history.replaceState({}, "", "/live?rotator=all");
  try {
    init();
    const selector = document.getElementById("camera-selector");
    selector.value = "cam1";
    selector.dispatchEvent(new Event("change"));
    jest.advanceTimersByTime(6000);
    expect(selector.value).toBe("cam1");
    expect(document.querySelector("video").src).toMatch(/\/clip\/cam1\?/);
    document.querySelector(".go-live-btn").click();
    const pending = document.getElementById("live-image-alt");
    expect(pending.src).toMatch(/\/stream\.mjpg\?camera=cam1&time=\d+$/);
    expect(new URLSearchParams(location.search).get("rotator")).toBeNull();
    expect(new URLSearchParams(location.search).get("camera")).toBe("cam1");
    jest.advanceTimersByTime(6000);
    expect(pending.src).toMatch(/\/stream\.mjpg\?camera=cam1&time=\d+$/);
    expect(selector.value).toBe("cam1");
  } finally {
    window.dispatchEvent(new Event("pagehide"));
    window.history.replaceState({}, "", "/");
    jest.useRealTimers();
  }
});

test("single live camera retries after fallback cooldown", async () => {
  jest.useFakeTimers();
  document.body.innerHTML = `
    <video id="live-video"><source></source></video>
  `;
  window.templateDetails = {
    cam1: { url: "sdm://example-home/device-1", capabilities: { live_video: true } },
  };
  global.fetch = jest.fn(() => Promise.resolve({ ok: true }));

  const originalLoad = window.HTMLMediaElement.prototype.load;
  let loadCount = 0;

  Object.defineProperty(window.HTMLMediaElement.prototype, "load", {
    configurable: true,
    value() {
      loadCount += 1;
      if (loadCount <= 2) {
        setTimeout(() => this.dispatchEvent(new Event("error")), 0);
      }
    },
  });
  window.history.replaceState({}, "", "/live?camera=cam1");

  try {
    init();
    jest.runOnlyPendingTimers();
    await Promise.resolve();
    const imageSources = Array.from(
      document.querySelectorAll("#live-image, #live-image-alt"),
    )
      .map((img) => img.src)
      .filter(Boolean);
    expect(
      imageSources.some((src) =>
        /\/stream\.mjpg\?camera=cam1&time=\d+$/.test(src),
      ),
    ).toBe(true);
    jest.advanceTimersByTime(20050);
    await Promise.resolve();
    expect(loadCount).toBeGreaterThanOrEqual(3);
  } finally {
    Object.defineProperty(window.HTMLMediaElement.prototype, "load", {
      configurable: true,
      value: originalLoad,
    });
    window.history.replaceState({}, "", "/");
  }
});
