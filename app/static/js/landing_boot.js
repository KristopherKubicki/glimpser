import { initNav } from "./nav.js";
import { initIndexTime } from "./time.js";
import { initLanding } from "./landing.js?v=20260930-private-rules";

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

// Landing kiosks should only boot the lightweight wall experience.
initNav({ passive: true });
initIndexTime();
initLanding();
initGuestGuard();
