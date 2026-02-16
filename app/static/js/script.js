import { initTemplates } from "./templates.js";
import { initVideoControls, initVisibilityHandler } from "./video.js";
import { initSchedulerToggle } from "./scheduler.js";
import {
  initDiscoveryToggle,
  initSubnetInput,
  initDiscoveryTable,
} from "./discovery.js";
import { initNav } from "./nav.js";
import { initFormValidation, initAddSettingValidation } from "./form.js";
import { initFooterFade } from "./footer.js";
import { initOffline } from "./offline.js";
import { initNotifications } from "./notifications.js";
import { initDangerToggle } from "./danger.js";
import { initIndexTime } from "./time.js";
import { initWelcome } from "./welcome.js";
import { initTooltips } from "./tooltips.js";
import { initCaptions } from "./captions.js";
import { initSettingsSearch, initShortcutPath } from "./settings.js";
import { initTabs } from "./tabs.js";
import { initThemeToggle, initContrastToggle } from "./theme.js";
import { initControlsDropdown } from "./controls.js";
import { initAutocomplete } from "./autocomplete.js";
import { initCosts } from "./costs.js";
import { initAdvanced } from "./advanced.js";
import { initKeyVisibility } from "./key_visibility.js";
import { initCliHelp } from "./cli_help.js";
import { initHotkeys } from "./hotkeys.js";
import { initNetworkBanner } from "./network_banner.js";
import { initUnsavedIndicator } from "./unsaved.js";
import { initVideoZoom } from "./zoom.js";
import { initSearchShortcut } from "./search_shortcut.js";
import { initUrlTester } from "./url_test.js";
import { initComfort } from "./comfort.js";

function initGuestGuard() {
  if (!window.IS_LAN_GUEST) return;
  document.addEventListener("click", (event) => {
    const target = event.target.closest("[data-requires-login]");
    if (!target) return;
    event.preventDefault();
    const nextUrl =
      target.getAttribute("data-login-next") ||
      target.getAttribute("href") ||
      window.location.pathname;
    const confirmed = window.confirm(
      "Login required for this action. Continue to the login screen?",
    );
    if (confirmed) {
      window.location.href = `/login?next=${encodeURIComponent(nextUrl)}`;
    }
  });
}

initTemplates();
initVideoControls();
initVisibilityHandler();
initSchedulerToggle();
initDiscoveryToggle();
initSubnetInput();
initDiscoveryTable();
initNav();
initFormValidation();
initAddSettingValidation();
initFooterFade();
initOffline();
initNotifications();
initDangerToggle();
initIndexTime();
initWelcome();
initTooltips();
initCaptions();
initSettingsSearch();
initShortcutPath();
initTabs();
initThemeToggle();
initContrastToggle();
initNetworkBanner();
initControlsDropdown();
initAutocomplete();
initCosts();
initAdvanced();
initKeyVisibility();
initUnsavedIndicator();
initCliHelp();
initVideoZoom();
initSearchShortcut();
initHotkeys();
initUrlTester();
initComfort();
initGuestGuard();
