import fs from "fs";
import path from "path";

test("service worker caches offline page", () => {
  const swPath = path.join("app", "static", "sw.js");
  const swText = fs.readFileSync(swPath, "utf8");
  expect(swText.includes("/offline")).toBe(true);
});

test("service worker caches only successful responses", () => {
  const swPath = path.join("app", "static", "sw.js");
  const swText = fs.readFileSync(swPath, "utf8");
  expect(swText.includes("if (response.ok)")).toBe(true);
});
