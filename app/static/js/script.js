import { initTemplates } from "./templates.js";
import { initVideoControls } from "./video.js";
import { initSchedulerToggle } from "./scheduler.js";
import { initDiscoveryToggle } from "./discovery.js";
import { initNav } from "./nav.js";
import { initFormValidation, initAddSettingValidation } from "./form.js";
import { initFooterFade } from "./footer.js";
import { initOffline } from "./offline.js";
import { initDangerToggle } from "./danger.js";
import { initIndexTime } from "./time.js";
import { initWelcome } from "./welcome.js";
import { initTooltips } from "./tooltips.js";
import { initCaptions } from "./captions.js";
import { initSettingsSearch } from "./settings.js";
import { initTabs } from "./tabs.js";
import { initThemeToggle } from "./theme.js";

function initNetworkBanner() {
  document.addEventListener("DOMContentLoaded", () => {
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

initTemplates();
initVideoControls();
initSchedulerToggle();
initDiscoveryToggle();
initNav();
initFormValidation();
initAddSettingValidation();
initFooterFade();
initOffline();
initDangerToggle();
initIndexTime();
initWelcome();
initTooltips();
initCaptions();
initSettingsSearch();
initTabs();
initThemeToggle();
initNetworkBanner();
