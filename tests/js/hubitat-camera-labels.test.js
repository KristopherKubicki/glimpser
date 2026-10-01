import { readFileSync } from "node:fs";

const source = readFileSync("app/utils/screenshots.py", "utf8");
const start = source.indexOf("    function imageLabelForItem(item, src) {");
const end = source.indexOf("    // The network wall", start);
const labelFor = new Function(
  "item",
  "src",
  "cameraLabels",
  "isMaterialIconLiteral",
  source.slice(start, end) + "\nreturn imageLabelForItem(item, src);",
);
const label = (path, labels = {}) =>
  labelFor(
    { innerText: "" },
    `https://example.invalid${path}`,
    labels,
    () => false,
  );

test("uses configured labels without interpolating script source", () => {
  expect(
    label("/clean_screenshot/ExampleDoor", {
      ExampleDoor: "</script><b>Entrance</b>",
    }),
  ).toBe("</script><b>Entrance</b>");
});
test("falls back to a readable camera name", () => {
  expect(label("/clean_screenshot/Example_Door")).toBe("Example Door");
});
test("malformed percent encoding does not abort dashboard cleanup", () => {
  expect(label("/clean_screenshot/Example%ZZ_Door")).toBe("Example%ZZ Door");
});
test("prototype properties cannot become labels", () => {
  expect(label("/clean_screenshot/toString")).toBe("toString");
});
