import { computeProgress } from "../../app/static/js/capture_status.js";

describe("computeProgress", () => {
  test("progress clamps between 0 and 1", () => {
    const next = 60000;
    expect(computeProgress(0, next, 1)).toBeCloseTo(0);
    expect(computeProgress(30000, next, 1)).toBeCloseTo(0.5);
    expect(computeProgress(60000, next, 1)).toBeCloseTo(1);
    expect(computeProgress(70000, next, 1)).toBeCloseTo(1);
  });
});
