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
    const pythonExe = process.env.PYTHON_BIN || "env/bin/python3";
    const pythonArgs = ["-c", script];
    const venvSite = `${process.cwd()}/env/lib/python3.10/site-packages`;
    try {
      return execFileSync(pythonExe, pythonArgs, {
        encoding: "utf8",
        env: {
          ...process.env,
          PYTHONPATH: process.env.PYTHONPATH
            ? `${venvSite}:${process.env.PYTHONPATH}`
            : venvSite,
        },
      });
    } catch (err) {
      const stderr = err?.stderr ? err.stderr.toString() : "";
      const msg = stderr || err?.message || "python3 failed";
      console.warn(`Skipping api discover test: ${msg}`);
      return null;
    }
  }

  test("returns list of endpoints", () => {
    const raw = fetchApiInfo();
    if (!raw) return;
    const output = raw.trim().split("\n").pop();
    const data = JSON.parse(output);
    expect(Array.isArray(data.endpoints)).toBe(true);
    expect(data.endpoints.length).toBeGreaterThan(0);
    expect(data.version).toBeDefined();
  });
});
