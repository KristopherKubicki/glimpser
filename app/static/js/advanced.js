export function initAdvanced() {
  document.addEventListener("DOMContentLoaded", () => {
    const toggle = document.getElementById("advanced-toggle");
    if (!toggle) return;
    const enabled = sessionStorage.getItem("advanced-enabled") === "true";
    if (enabled) {
      toggle.checked = true;
      document.body.classList.add("advanced-enabled");
    }

    const update = () => {
      const state = toggle.checked;
      document.body.classList.toggle("advanced-enabled", state);
      sessionStorage.setItem("advanced-enabled", String(state));
    };

    toggle.addEventListener("change", update);
  });
}
