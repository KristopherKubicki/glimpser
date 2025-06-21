export function initPasswordToggle() {
  const setup = () => {
    const toggle = document.getElementById("password-toggle");
    const input = document.getElementById("password");
    if (!toggle || !input) return;
    const useEl = toggle.querySelector("use");
    const sprite = useEl ? useEl.getAttribute("href").split("#")[0] : "";
    const show = () => {
      input.type = "text";
      if (useEl) {
        useEl.setAttribute("href", `${sprite}#eye-off`);
      }
    };
    const hide = () => {
      input.type = "password";
      if (useEl) {
        useEl.setAttribute("href", `${sprite}#eye`);
      }
    };
    toggle.addEventListener("mousedown", show);
    toggle.addEventListener("touchstart", show);
    toggle.addEventListener("mouseup", hide);
    toggle.addEventListener("mouseleave", hide);
    toggle.addEventListener("touchend", hide);
    toggle.addEventListener("touchcancel", hide);
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", setup);
  } else {
    setup();
  }
}

initPasswordToggle();
