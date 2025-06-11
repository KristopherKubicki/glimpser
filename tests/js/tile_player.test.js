import { jest } from "@jest/globals";

document.body.innerHTML = `
  <video id="live-video"><source></source></video>
  <select id="camera-selector">
    <option value="cam1">cam1</option>
    <option value="cam2">cam2</option>
  </select>
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
