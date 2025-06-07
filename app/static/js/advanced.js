export function initAdvanced() {
  document.addEventListener("DOMContentLoaded", () => {
    const btn = document.getElementById("advanced-toggle");
    if (!btn) return;
    if (sessionStorage.getItem("advanced-enabled") === "true") {
      document.body.classList.add("advanced-enabled");
    }
    btn.addEventListener("click", () => {
      const enabled = document.body.classList.toggle("advanced-enabled");
      sessionStorage.setItem("advanced-enabled", String(enabled));
    });
  });
}
