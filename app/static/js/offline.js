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

  navigator.serviceWorker
    .register("/sw.js")
    .then(async () => {
      const profile = new URLSearchParams(window.location.search).get(
        "profile",
      );
      if (
        window.location.pathname !== "/" ||
        !["office", "living"].includes(profile)
      )
        return;
      const registration = await navigator.serviceWorker.ready;
      let retryTimer, replyTimer, channel;
      let stopped = false;
      const finish = (ready) => {
        clearTimeout(replyTimer);
        channel?.port1.close();
        channel = undefined;
        document.documentElement.dataset.kioskOfflineReady = String(ready);
        if (!ready && !stopped) retryTimer = setTimeout(prepare, 60000);
      };
      const prepare = () => {
        if (stopped || channel) return;
        clearTimeout(retryTimer);
        const worker =
          navigator.serviceWorker.controller || registration.active;
        if (!worker || typeof MessageChannel !== "function") return;
        const urls = [
          window.location.href,
          ...performance
            .getEntriesByType("resource")
            .map((entry) => entry.name)
            .filter((value) => {
              const url = new URL(value);
              return (
                url.origin === window.location.origin &&
                url.pathname.startsWith("/static/")
              );
            }),
        ];
        channel = new MessageChannel();
        // A server restart or a lost worker reply must not leave warm-up stuck.
        document.documentElement.dataset.kioskOfflineReady = "false";
        replyTimer = setTimeout(() => finish(false), 15000);
        channel.port1.onmessage = (event) => {
          finish(event.data?.ready === true);
        };
        try {
          worker.postMessage(
            { type: "CACHE_KIOSK_SHELL", urls: [...new Set(urls)] },
            [channel.port2],
          );
        } catch {
          finish(false);
        }
      };
      window.addEventListener("online", prepare);
      navigator.serviceWorker.addEventListener("controllerchange", prepare);
      window.addEventListener(
        "pagehide",
        () => {
          stopped = true;
          clearTimeout(retryTimer);
          clearTimeout(replyTimer);
          channel?.port1.close();
          window.removeEventListener("online", prepare);
          window.removeEventListener("load", prepare);
          navigator.serviceWorker.removeEventListener(
            "controllerchange",
            prepare,
          );
        },
        { once: true },
      );
      if (document.readyState === "complete") prepare();
      else window.addEventListener("load", prepare, { once: true });
    })
    .catch((err) =>
      // Keep logs quiet on self-signed/mismatched HTTPS setups where service
      // worker install can fail even though the app itself still works.
      console.warn("Service worker unavailable:", err?.message || err),
    );
}
