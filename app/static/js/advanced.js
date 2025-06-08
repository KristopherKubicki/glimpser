export function initAdvanced() {
  document.addEventListener("DOMContentLoaded", () => {
    const toggle = document.getElementById("advanced-toggle");
    const locked = document.querySelectorAll("[data-locked]");
    const applyState = (state) => {
      document.body.classList.toggle("advanced-enabled", state);
      sessionStorage.setItem("advanced-enabled", String(state));
      locked.forEach((el) => {
        el.disabled = !state;
      });
    };

    if (!toggle) {
      applyState(false);
      return;
    }

    const enabled = sessionStorage.getItem("advanced-enabled") === "true";
    toggle.checked = enabled;
    applyState(enabled);

    toggle.addEventListener("change", () => applyState(toggle.checked));
  });
}
