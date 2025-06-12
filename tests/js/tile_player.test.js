import { jest } from "@jest/globals";

document.body.innerHTML = `
  <video id="live-video"><source></source></video>
`;

window.templateDetails = { cam1: {}, cam2: {} };

let init;
beforeAll(async () => {
  const mod = await import("../../app/static/js/tile_player.js");
  init = mod.initTilePlayer;
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
