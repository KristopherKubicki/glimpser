import { jest } from "@jest/globals";
import { adjustFullHeight } from "../../app/static/js/tile_player.js";

beforeEach(() => {
  document.body.innerHTML =
    '<header></header><div id="network-banner"></div><div class="video-container full-height"></div>';
  Object.defineProperty(window, "innerHeight", {
    configurable: true,
    value: 800,
  });
  Object.defineProperty(window, "innerWidth", {
    configurable: true,
    value: 1200,
  });
  Object.defineProperty(document.querySelector("header"), "offsetHeight", {
    value: 80,
  });
  Object.defineProperty(
    document.getElementById("network-banner"),
    "offsetHeight",
    { value: 30 },
  );
  Object.defineProperty(document, "fullscreenElement", {
    configurable: true,
    value: null,
  });
  document.documentElement.style.setProperty("--footer-space", "60px");
});
afterEach(() => {
  document.documentElement.removeAttribute("style");
  Object.defineProperty(document, "fullscreenElement", {
    configurable: true,
    value: null,
  });
});
test("normal desktop playback reserves header, banner and footer space", () => {
  adjustFullHeight();
  expect(document.querySelector(".full-height").style.height).toBe("630px");
});
test.each([1200, 390])(
  "fullscreen fills the viewport at width %s and restores normal layout on exit",
  (width) => {
    Object.defineProperty(window, "innerWidth", {
      configurable: true,
      value: width,
    });
    const player = document.querySelector(".full-height");
    Object.defineProperty(document, "fullscreenElement", {
      configurable: true,
      value: player,
    });
    document.dispatchEvent(new Event("fullscreenchange"));
    expect(player.style.height).toBe("800px");
    expect(player.style.maxHeight).toBe("800px");
    Object.defineProperty(document, "fullscreenElement", {
      configurable: true,
      value: null,
    });
    document.dispatchEvent(new Event("fullscreenchange"));
    expect(player.style.height).toBe(width >= 768 ? "630px" : "auto");
    expect(player.style.maxHeight).toBe("630px");
  },
);
test("a small viewport never produces a negative player height", () => {
  Object.defineProperty(window, "innerHeight", {
    configurable: true,
    value: 100,
  });
  adjustFullHeight();
  expect(document.querySelector(".full-height").style.maxHeight).toBe("0px");
});
