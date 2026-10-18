import {
  createRotationBalance,
  rotationCategory,
} from "../../app/static/js/landing.js";
const scene = (name, group = "Systems") => ({
  dataset: { heroName: name },
  querySelector: () => ({ dataset: { areaLabel: group } }),
});
const storage = () => {
  const data = new Map();
  return {
    getItem: (key) => data.get(key),
    setItem: (key, value) => data.set(key, value),
  };
};
test("variety chooses another category among equally overdue views", () => {
  const pool = [scene("A"), scene("B"), scene("C", "Weather")];
  const planner = createRotationBalance("office", storage());
  expect(planner.queue(pool, 0, () => false, 2)).toEqual([2, 1]);
});
test.each(["office", "living", "hal"])(
  "%s eventually shows every view despite an uneven category mix",
  (profile) => {
    const pool = Array.from({ length: 220 }, (_, i) =>
      scene(String(i), i < 180 ? "Systems" : i < 210 ? "Weather" : "Home"),
    );
    const planner = createRotationBalance(profile, storage());
    const shown = new Set();
    let current = 0;
    for (let i = 0; i < 240; i++) {
      shown.add(current);
      planner.viewed(pool[current]);
      current = planner.queue(pool, current, () => false, 1)[0];
    }
    expect(shown.size).toBe(220);
  },
);
test("reload preserves fairness by camera name; profiles remain separate", () => {
  const saved = storage();
  const pool = ["A", "B", "C", "D"].map((name) => scene(name));
  const planner = createRotationBalance("hal", saved);
  planner.viewed(pool[1]);
  planner.viewed(pool[2]);
  const restored = createRotationBalance("hal", saved);
  expect(restored.queue(pool, 0, () => false, 1)).toEqual([3]);
  expect(
    createRotationBalance("living", saved).queue(pool, 0, () => false, 1),
  ).toEqual([1]);
});
test("preview planning does not count unshown views and excludes failures", () => {
  const saved = storage();
  const planner = createRotationBalance("office", saved);
  const pool = ["A", "B", "C"].map((name) => scene(name));
  const first = planner.queue(pool, 0, (s) => s.dataset.heroName === "B", 4);
  expect(first).toEqual([2]);
  expect(planner.queue(pool, 0, (s) => s.dataset.heroName === "B", 4)).toEqual(
    first,
  );
  expect(saved.getItem("glimpser.office.rotation-history.v1")).toBeUndefined();
  expect(planner.queue(pool, 0, () => true, 4)).toEqual([]);
});
test("unavailable or malformed storage is safe, history stays bounded", () => {
  const unavailable = {
    getItem() {
      throw Error("blocked");
    },
    setItem() {
      throw Error("quota");
    },
  };
  const planner = createRotationBalance("hal", unavailable);
  expect(() => planner.viewed(scene("A"))).not.toThrow();
  expect(planner.queue([scene("A"), scene("B")], 0, () => false, 1)).toEqual([
    1,
  ]);
  const saved = storage();
  saved.setItem(
    "glimpser.hal.rotation-history.v1",
    '[null,["bad",-2],["wrong","x"]]',
  );
  const bounded = createRotationBalance("hal", saved);
  for (let i = 0; i < 600; i++) bounded.viewed(scene(String(i)));
  expect(
    JSON.parse(saved.getItem("glimpser.hal.rotation-history.v1")),
  ).toHaveLength(512);
  expect(createRotationBalance("public", saved)).toBeNull();
});
test("uses existing visible group metadata", () => {
  expect(rotationCategory(scene("A", "Hubitat"))).toBe("systems");
  expect(rotationCategory(scene("B", "Marine"))).toBe("lake");
  expect(rotationCategory(scene("C", "Cosmic"))).toBe("science");
});
