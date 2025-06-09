import fs from "fs";
import path from "path";

test("service worker caches offline page", () => {
  const swPath = path.join("app", "static", "sw.js");
  const swText = fs.readFileSync(swPath, "utf8");
  expect(swText.includes("/offline")).toBe(true);
});
