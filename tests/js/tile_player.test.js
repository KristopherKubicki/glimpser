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

test("loads first camera", () => {
  init();
  const src = document.querySelector("#live-video source").src;
  expect(src).toMatch(/\/last_video\/cam1$/);
});

test("swaps to clip after preload", async () => {
  const video = document.getElementById("live-video");
  video.load = jest.fn(() => {
    video.dispatchEvent(new Event("loadedmetadata"));
  });

  global.fetch = jest.fn(() =>
    Promise.resolve({
      ok: true,
      blob: () => Promise.resolve(new Blob(["hi"], { type: "video/mp4" })),
    }),
  );

  init();
  await Promise.resolve();
  await Promise.resolve();
  expect(fetch).toHaveBeenCalledWith("/clip/cam1", expect.any(Object));
});

test("group change updates video src", () => {
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
  const src = document.querySelector("#live-video source").src;
  const hd = document.querySelector("#live-video").dataset.hdSrc;
  expect(src).toMatch(/\/last_teaser\?group=kitchen$/);
  expect(hd).toMatch(/\/stream.mp4\?group=kitchen$/);
});

test("fallback to nav camera dropdown", () => {
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
  const src = document.querySelector("#live-video source").src;
  expect(src).toMatch(/\/last_teaser\?group=foo$/);
});
