export function sendTelemetry(event, data = {}) {
  if (typeof fetch !== "function") return;
  const result = fetch("/telemetry", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ event, data }),
  });
  if (result && typeof result.catch === "function") {
    result.catch(() => {});
  }
}
