export function initOffline() {
  const host = String(window.location.hostname || "").toLowerCase();
  const isLocalHost =
    host === "localhost" || host === "127.0.0.1" || host === "::1";
  const hasSecureScheme = window.location.protocol === "https:";
  const canUseServiceWorker =
    "serviceWorker" in navigator &&
    (window.isSecureContext || hasSecureScheme || isLocalHost);

  if (!canUseServiceWorker) {
    return;
  }

  navigator.serviceWorker.register("/sw.js").catch((err) =>
    // Keep logs quiet on self-signed/mismatched HTTPS setups where service
    // worker install can fail even though the app itself still works.
    console.warn("Service worker unavailable:", err?.message || err),
  );
}
