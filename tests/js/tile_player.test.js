import { jest } from "@jest/globals";

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
  expect(img.src).toMatch(/\/stream\.mjpg\?group=all&time=\d+$/);
  jest.advanceTimersByTime(30000);
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
  expect(img.src).toMatch(/\/stream\.mjpg\?group=all&time=\d+$/);
  jest.advanceTimersByTime(30000);
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
