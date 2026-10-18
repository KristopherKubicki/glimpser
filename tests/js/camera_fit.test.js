import { cameraObjectFit, fitCameraMedia } from "../../app/static/js/camera_fit.js";

test("limits camera edge cropping to eight percent", () => {
  expect(cameraObjectFit(1600, 900, 1600, 900)).toBe("cover");
  expect(cameraObjectFit(1600, 900, 1600, 1200)).toBe("contain");
  expect(cameraObjectFit(0, 900, 1600, 900)).toBe("contain");
});

test("disabled fitting clears an earlier override", () => {
  const media = document.createElement("video");
  media.style.objectFit = "cover";
  fitCameraMedia(media, document.createElement("div"), false);
  expect(media.style.objectFit).toBe("");
});
