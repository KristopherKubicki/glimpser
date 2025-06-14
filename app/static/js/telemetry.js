export function sendTelemetry(event, data = {}) {
  try {
    const p = fetch("/telemetry", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ event, data }),
    });
    if (p && typeof p.catch === "function") p.catch(() => {});
  } catch {
    // Ignore network errors or missing fetch
  }
}
