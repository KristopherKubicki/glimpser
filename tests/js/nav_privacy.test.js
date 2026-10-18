import { visibleGroups } from "../../app/static/js/nav.js";

test("navigation favorites are installation configured and inventory limited", () => {
  expect(
    visibleGroups(["all", "site", "weather", "active"], "active", false, [
      "site",
      "missing",
    ]),
  ).toEqual(["all", "site", "active"]);
});

test("expanded navigation retains all inventory groups", () => {
  expect(visibleGroups(["all", "site"], null, true, [])).toEqual([
    "all",
    "site",
  ]);
});

test("unconfigured navigation uses generic categories", () => {
  expect(visibleGroups(["all", "private-site", "weather"], null)).toEqual([
    "all",
    "weather",
  ]);
});
