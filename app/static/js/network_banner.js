export function initNetworkBanner() {
  const setup = () => {
    if (typeof window.IS_LOGGED_IN !== "undefined" && !window.IS_LOGGED_IN) {
      return;
    }

    const banner = document.getElementById("network-banner");
    if (!banner) return;
    const isLivePage = window.location?.pathname === "/live";
    if (isLivePage) return;
    const offlineThreshold = isLivePage ? 3 : 1;
    const offlineText = isLivePage
      ? "Connection check failing"
      : "Offline mode";
    let consecutiveMisses = 0;
    let pollTimer = null;
    let activeCheck = null;
    let disposed = false;

    const updateBanner = (isOnline) => {
      if (isOnline) {
        banner.classList.remove("show");
        banner.textContent = "";
      } else {
        banner.textContent = offlineText;
        banner.classList.add("show");
      }
    };

    const markHealthy = () => {
      consecutiveMisses = 0;
      updateBanner(true);
    };

    const markMiss = () => {
      consecutiveMisses += 1;
      if (consecutiveMisses >= offlineThreshold) {
        updateBanner(false);
      }
    };

    const checkStatus = async () => {
      if (disposed) return;
      const ctl = new AbortController();
      activeCheck = ctl;
      let timeoutId = null;
      try {
        timeoutId = setTimeout(() => ctl.abort(), 4000);
        const res = await fetch("/network_status", {
          cache: "no-store",
          headers: { Accept: "application/json" },
          signal: ctl.signal,
        });
        const data = await res.json();
        if (data.online) {
          markHealthy();
        } else {
          markMiss();
        }
      } catch {
        if (!disposed) {
          markMiss();
        }
      } finally {
        if (timeoutId) {
          clearTimeout(timeoutId);
        }
        if (activeCheck === ctl) {
          activeCheck = null;
        }
      }
    };

    if (navigator.onLine) {
      markHealthy();
    } else if (!isLivePage) {
      updateBanner(false);
      consecutiveMisses = offlineThreshold;
    }

    const onOnline = () => markHealthy();
    const onOffline = () => markMiss();
    const cleanup = () => {
      disposed = true;
      if (pollTimer) {
        clearInterval(pollTimer);
        pollTimer = null;
      }
      if (activeCheck) {
        activeCheck.abort();
        activeCheck = null;
      }
      window.removeEventListener("online", onOnline);
      window.removeEventListener("offline", onOffline);
    };

    window.addEventListener("online", onOnline);
    window.addEventListener("offline", onOffline);
    window.addEventListener("pagehide", cleanup, { once: true });

    checkStatus();
    pollTimer = setInterval(checkStatus, 10000);
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", setup, { once: true });
  } else {
    setup();
  }
}
