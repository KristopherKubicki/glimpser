export function initAdvanced() {
  document.addEventListener("DOMContentLoaded", () => {
    const btn = document.getElementById("advanced-toggle");
    if (!btn) return;
    btn.addEventListener("click", () => {
      document.body.classList.toggle("advanced-enabled");
    });
  });
}
