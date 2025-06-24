import { getCameraNames } from "../../app/static/js/camera_utils.js";

describe("getCameraNames util", () => {
  test("returns camera names without groups", () => {
    const details = {
      cam1: {},
      cam2: {},
      "group-test": {},
      All: {},
    };
    expect(getCameraNames(details)).toEqual(["cam1", "cam2"]);
  });
});
