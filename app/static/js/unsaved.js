export function initUnsavedIndicator() {
  document.addEventListener("DOMContentLoaded", () => {
    const form = document.getElementById("settings-form");
    const icon = document.getElementById("unsaved-icon");
    if (!form || !icon) return;
    form.addEventListener("input", () => {
      icon.classList.remove("hidden");
    });
    form.addEventListener("submit", () => {
      icon.classList.add("hidden");
    });
  });
}
