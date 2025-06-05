export function initThemeToggle() {
  document.addEventListener("DOMContentLoaded", () => {
    const toggle = document.getElementById("theme-toggle");
    if (!toggle) return;

    const useEl = toggle.querySelector("use");
    if (!useEl) return;
    const sprite = useEl.getAttribute("href").split("#")[0];

    const applyTheme = (theme) => {
      document.body.classList.toggle("light-mode", theme === "light");
      useEl.setAttribute(
        "href",
        `${sprite}#${theme === "light" ? "moon" : "sun"}`,
      );
    };

    let current =
      localStorage.getItem("theme") ||
      (window.matchMedia("(prefers-color-scheme: light)").matches
        ? "light"
        : "dark");
    applyTheme(current);

    toggle.addEventListener("click", (e) => {
      e.preventDefault();
      current = current === "light" ? "dark" : "light";
      localStorage.setItem("theme", current);
      applyTheme(current);
    });
  });
}
