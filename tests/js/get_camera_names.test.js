import { jest } from "@jest/globals";

document.body.innerHTML = `
  <div id="video-overlay"></div>
  <img id="live-image" />
  <video id="live-video"></video>
  <div id="template-details"></div>
  <div id="speed-container"></div>
  <input id="speed-slider" />
  <span id="speed-value"></span>
  <div id="loading-indicator"></div>
  <div id="play-pause-indicator"></div>
  <div id="offline-indicator"></div>
  <div id="offline-message"></div>
  <div id="capture-error-indicator"></div>
  <div id="capture-error-message"></div>
  <div id="stream-error-indicator"></div>
  <div id="stream-error-message"></div>
  <div id="error-message"></div>
  <button id="play-pause"></button>
  <div id="toggle-details"></div>
  <input id="seek-bar" />
  <div id="jog-shuttle"></div>
  <select id="video-source"><option value="mjpg">MJPG</option></select>
  <select id="camera-selector"></select>
  <select id="group-selector"></select>
`;

window.templateDetails = {
  cam1: { last_screenshot_time: "2023-01-01 00:00:00" },
  cam2: { last_screenshot_time: "2023-01-01 00:00:00" },
};

describe("getCameraNames", () => {
  let getCameraNames;
  let changeCamera;
  beforeAll(async () => {
    const mod = await import("../../app/static/js/live.js");
    getCameraNames = mod.getCameraNames;
    changeCamera = window.changeCamera;
  });

  test("filters out group entries", () => {
    const selector = document.getElementById("camera-selector");
    selector.innerHTML = `
      <option value="All">All</option>
      <option value="group-test">group-test</option>
      <option value="cam1">cam1</option>
      <option value="cam2">cam2</option>
    `;
    selector.value = "group-test";
    changeCamera();

    selector.value = "All";
    changeCamera();

    expect(getCameraNames()).toEqual(["cam1", "cam2"]);
    expect(window.templateDetails["All"].groupCameras).toEqual([
      "cam1",
      "cam2",
    ]);
  });
});
