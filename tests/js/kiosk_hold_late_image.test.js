import { createKioskHold } from "../../app/static/js/kiosk_hold.js";
import { jest } from "@jest/globals";
afterEach(() => {
  jest.restoreAllMocks();
  localStorage.clear();
});
test("online feed interruption is not described as offline", () => {
  Object.defineProperty(navigator, "onLine", {
    configurable: true,
    value: true,
  });
  const stage = document.createElement("div");
  document.body.append(stage);
  const hold = createKioskHold(stage, "test");
  hold.hold("Capture service unavailable");
  expect(stage.textContent).toContain("FEED INTERRUPTED");
  expect(stage.textContent).not.toContain("KIOSK OFFLINE");
  hold.recover();
});
test("browser offline is explicitly labeled", () => {
  Object.defineProperty(navigator, "onLine", {
    configurable: true,
    value: false,
  });
  const stage = document.createElement("div");
  document.body.append(stage);
  const hold = createKioskHold(stage, "test");
  hold.hold("No connection");
  expect(stage.textContent).toContain("KIOSK OFFLINE");
  hold.recover();
});
test("a frame arriving after a status timeout fills the saved view without clearing the warning", () => {
  Object.defineProperty(navigator, "onLine", {
    configurable: true,
    value: true,
  });
  jest
    .spyOn(HTMLCanvasElement.prototype, "getContext")
    .mockReturnValue({ drawImage: jest.fn() });
  jest
    .spyOn(HTMLCanvasElement.prototype, "toDataURL")
    .mockReturnValue("data:image/jpeg;base64,abcd");
  const stage = document.createElement("div");
  document.body.append(stage);
  const scene = document.createElement("section");
  scene.dataset.heroName = "BandwidthTX";
  const image = {
    naturalWidth: 900,
    naturalHeight: 260,
    src: "/clean_screenshot/BandwidthTX?capture=2026-09-25",
    dataset: { expectedCaptureTime: "2026-09-25 19:57:11" },
  };
  const hold = createKioskHold(stage, "timeout-test");
  hold.hold("Status request delayed");
  expect(stage.querySelector("img")).toBeNull();
  hold.remember(image, scene);
  expect(hold.active).toBe(true);
  expect(stage.querySelector("img").src).toBe("data:image/jpeg;base64,abcd");
  expect(stage.textContent).toContain("Saved view: BandwidthTX");
  expect(stage.textContent).toContain("Status request delayed");
  expect(stage.textContent).not.toContain("No saved image");
  hold.recover();
  expect(stage.querySelector(".kiosk-offline-view")).toBeNull();
});
