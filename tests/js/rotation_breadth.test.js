import {
  restoreOfficeRotation,
  rememberOfficeRotation,
} from "../../app/static/js/landing.js";
test.each(["office", "living", "hal"])(
  "%s resumes by camera after the pool reorders",
  (profile) => {
    window.localStorage.clear();
    rememberOfficeRotation(
      { dataset: { heroName: "HouseSystemsMap" } },
      profile,
    );
    const scenes = [
      { dataset: { heroName: "Other" } },
      { dataset: { heroName: "HouseSystemsMap" } },
    ];
    expect(restoreOfficeRotation(scenes, profile)).toBe(1);
    expect(restoreOfficeRotation(scenes.reverse(), profile)).toBe(0);
    expect(
      restoreOfficeRotation(
        [{ dataset: { heroName: "Unavailable replacement" } }],
        profile,
      ),
    ).toBe(-1);
  },
);
test("public rotation does not inherit a private room cursor", () => {
  rememberOfficeRotation(
    { dataset: { heroName: "HouseSystemsMap" } },
    "public",
  );
  expect(
    restoreOfficeRotation(
      [{ dataset: { heroName: "HouseSystemsMap" } }],
      "public",
    ),
  ).toBe(-1);
});

const scene = (name) => ({ dataset: { heroName: name } });
test.each(["office", "living", "hal"])(
  "%s continues after a missing next camera",
  (profile) => {
    window.localStorage.clear();
    const original = ["A", "B", "C", "D"].map(scene);
    rememberOfficeRotation(original[1], profile, original);
    expect(restoreOfficeRotation(["D", "A", "C"].map(scene), profile)).toBe(2);
    expect(restoreOfficeRotation(["A", "D"].map(scene), profile)).toBe(1);
    expect(restoreOfficeRotation(["Replacement"].map(scene), profile)).toBe(-1);
  },
);
test("fallback wraps and remains bounded for large rotations", () => {
  window.localStorage.clear();
  const pool = Array.from({ length: 220 }, (_, i) => scene(String(i)));
  rememberOfficeRotation(pool[219], "hal", pool);
  const saved = JSON.parse(
    window.localStorage.getItem("glimpser.hal.upcoming-cameras.v1"),
  );
  expect(saved).toHaveLength(12);
  expect(saved.slice(0, 3)).toEqual(["219", "0", "1"]);
  expect(restoreOfficeRotation([scene("1")], "hal")).toBe(0);
  expect(restoreOfficeRotation([scene("1")], "living")).toBe(-1);
});
test("invalid fallback data cannot interrupt rotation", () => {
  window.localStorage.clear();
  for (const invalid of ["{", "{}", "null", "[null,123]"]) {
    window.localStorage.setItem("glimpser.hal.upcoming-cameras.v1", invalid);
    expect(restoreOfficeRotation([scene("A")], "hal")).toBe(-1);
  }
});
