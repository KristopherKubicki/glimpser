export function initNetworkBanner() {
  document.addEventListener("DOMContentLoaded", () => {
    if (typeof window.IS_LOGGED_IN !== "undefined" && !window.IS_LOGGED_IN) {
      return;
    }

    const banner = document.getElementById("network-banner");
    if (!banner) return;

    const checkStatus = async () => {
      try {
        const res = await fetch("/network_status");
        const data = await res.json();
        if (data.online) {
          banner.classList.remove("show");
          banner.textContent = "";
        } else {
          banner.textContent = "Offline mode";
          banner.classList.add("show");
        }
      } catch {
        banner.textContent = "Offline mode";
        banner.classList.add("show");
      }
    };

    checkStatus();
    setInterval(checkStatus, 10000);
  });
}
