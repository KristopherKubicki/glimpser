import { jest } from "@jest/globals";

// setup DOM
Document.prototype.createRange = function () {
  return {
    setStart: () => {},
    setEnd: () => {},
    commonAncestorContainer: document.createElement("div"),
  };
};

Object.defineProperty(window.HTMLMediaElement.prototype, "load", {
  configurable: true,
  value: jest.fn(),
});
Object.defineProperty(window.HTMLMediaElement.prototype, "play", {
  configurable: true,
  value: jest.fn(() => Promise.resolve()),
});

document.body.innerHTML = `
  <video id="vid"></video>
  <img id="img" />
`;

jest.useFakeTimers();

describe("initClipPlayer", () => {
  test("sets clip and poster", async () => {
    const mod = await import("../../app/static/js/clip_player.js");
    mod.initClipPlayer({
      cameras: ["cam1"],
      videoId: "vid",
      posterId: "img",
      refresh: 0,
    });
    document.dispatchEvent(new Event("DOMContentLoaded"));
    jest.runAllTimers();
    const vid = document.getElementById("vid");
    const img = document.getElementById("img");
    expect(vid.src).toContain("/clip/cam1");
    expect(img.src).toContain("/last_screenshot/cam1");
  });
});
