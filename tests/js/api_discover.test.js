import { execFileSync } from "child_process";

describe("API discover", () => {
  function fetchApiInfo() {
    const script = [
      "import json, os",
      'os.environ["LOG_LEVEL"] = "CRITICAL"',
      "from app import create_app",
      "app = create_app(enable_watchdog=False, schedule=False, crawlers=False, log_cache=False)",
      "client = app.test_client()",
      'print(json.dumps(client.get("/api/discover").get_json()))',
    ].join("; ");
    return execFileSync("python3", ["-c", script], { encoding: "utf8" });
  }

  test("returns list of endpoints", () => {
    const output = fetchApiInfo().trim().split("\n").pop();
    const data = JSON.parse(output);
    expect(Array.isArray(data.endpoints)).toBe(true);
    expect(data.endpoints.length).toBeGreaterThan(0);
    expect(data.version).toBeDefined();
  });
});
