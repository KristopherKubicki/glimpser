import { jest } from "@jest/globals";

let computeBorderColor;

beforeAll(async () => {
  const mod = await import("../../app/static/js/templates.js");
  computeBorderColor = mod.computeBorderColor;
});

describe("computeBorderColor", () => {
  test("recent capture is full blue", () => {
    expect(computeBorderColor(0.5, false)).toBe("rgba(26, 115, 232, 1)");
  });
  test("after five minutes color halves", () => {
    expect(computeBorderColor(5, false)).toBe("rgba(26, 115, 232, 0.5)");
  });
  test("after fifty minutes color quarters", () => {
    expect(computeBorderColor(50, false)).toBe("rgba(26, 115, 232, 0.25)");
  });
  test("error uses gray base", () => {
    expect(computeBorderColor(0, true)).toBe("rgba(128, 128, 128, 1)");
  });
});
