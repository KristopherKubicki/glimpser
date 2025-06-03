export function initOffline() {
  const checkbox = document.getElementById("offline-preview");
  if (!checkbox) return;

  checkbox.checked = localStorage.getItem("offlinePreviewEnabled") === "true";

  checkbox.addEventListener("change", () => {
    if (checkbox.checked) {
      localStorage.setItem("offlinePreviewEnabled", "true");
      registerSW();
    } else {
      localStorage.removeItem("offlinePreviewEnabled");
      unregisterSW();
    }
  });

  if (checkbox.checked) {
    registerSW();
  }
}

function registerSW() {
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/sw.js").catch(console.error);
  }
}

function unregisterSW() {
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.getRegistrations().then((regs) => {
      regs.forEach((reg) => {
        if (reg.active && reg.active.scriptURL.includes("sw.js")) {
          reg.unregister();
        }
      });
    });
  }
}
