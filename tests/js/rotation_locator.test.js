import { locatorModel } from "../../app/static/js/rotation_locator.js";

test("mixed sites have no misleading location anchor", () => {
  const catalogs = [{dashboard: "property", cameras: [
    {name:"Door", group:"Home"}, {name:"Entry",group:"Shop"}
  ]}];
  expect(locatorModel(catalogs, ["Door", "Entry"])).toBeNull();
});
test("missing coordinates retain a bounded schematic", () => {
  const catalogs = [{dashboard: "property", cameras: [
    {name:"Door", group:"Home"}, {name:"Yard",group:"Home"}
  ]}];
  const model = locatorModel(catalogs, ["Door"]);
  expect(model.group).toBe("Home");
  expect(model.points).toHaveLength(2);
  expect(model.points.every(p => Number.isFinite(p.x) && Number.isFinite(p.y))).toBe(true);
});
