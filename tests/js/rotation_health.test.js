import { updateLandingAvailability } from "../../app/static/js/landing.js";
const makeScenes = () =>
  ["A", "B", "C", "D"].map((heroName) => ({ dataset: { heroName } }));
const suppressed = (scene) =>
  scene.dataset.landingFeedUnavailable === "true" ||
  scene.dataset.testWeak === "true";

test.each(["office", "living", "hal"])(
  "%s skips forward when the current feed fails",
  (profile) => {
    const scenes = makeScenes();
    expect(
      updateLandingAvailability(
        scenes,
        2,
        ["A", "B", "D"],
        profile,
        suppressed,
      ),
    ).toBe(3);
    expect(scenes[2].dataset.landingFeedUnavailable).toBe("true");
    expect(
      updateLandingAvailability(scenes, 3, ["A", "B"], profile, suppressed),
    ).toBe(0);
  },
);
test("healthy current view stays put; temporarily weak frames remain excluded", () => {
  const scenes = makeScenes();
  scenes[3].dataset.testWeak = "true";
  expect(
    updateLandingAvailability(
      scenes,
      1,
      ["A", "B", "C", "D"],
      "office",
      suppressed,
    ),
  ).toBe(1);
  expect(
    updateLandingAvailability(scenes, 2, ["A", "D"], "office", suppressed),
  ).toBe(0);
});
test("an empty pool holds instead of replaying rejected feeds, then recovers", () => {
  const scenes = makeScenes();
  expect(updateLandingAvailability(scenes, 2, [], "hal", suppressed)).toBe(-1);
  expect(scenes.every(suppressed)).toBe(true);
  expect(updateLandingAvailability(scenes, 2, ["D"], "hal", suppressed)).toBe(
    3,
  );
  expect(suppressed(scenes[3])).toBe(false);
});
test("missing metadata and public profiles cannot change availability", () => {
  const scenes = makeScenes();
  for (const available of [null, undefined, {}]) {
    expect(
      updateLandingAvailability(scenes, 2, available, "hal", suppressed),
    ).toBe(null);
  }
  expect(updateLandingAvailability(scenes, 2, [], "public", suppressed)).toBe(
    null,
  );
  expect(
    scenes.every((s) => s.dataset.landingFeedUnavailable === undefined),
  ).toBe(true);
});
