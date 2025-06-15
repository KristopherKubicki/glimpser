export function sendTelemetry(event, data = {}) {
  const result =
    typeof fetch === "function"
      ? fetch("/telemetry", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ event, data }),
        })
      : null;
  if (result && typeof result.catch === "function") {
    result.catch(() => {});
  }
}
