/**
 * Toggle advanced mode for the current session.
 *
 * The state is persisted in `sessionStorage` as "advanced-enabled" so
 * user preference survives page reloads until the session ends.
 */
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

    toggle.addEventListener("change", () => {
      if (toggle.checked) {
        alert("Be careful! Advanced mode can damage your system or database.");
      }
      applyState(toggle.checked);
    });
  });
}
