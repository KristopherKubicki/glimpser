export function initThemeToggle() {
  document.addEventListener("DOMContentLoaded", () => {
    const toggle = document.getElementById("theme-toggle");
    const useEl = toggle?.querySelector("use");
    const sprite = useEl ? useEl.getAttribute("href").split("#")[0] : "";

    const applyTheme = (theme) => {
      document.body.classList.toggle("light-mode", theme === "light");
      if (useEl) {
        useEl.setAttribute(
          "href",
          `${sprite}#${theme === "light" ? "moon" : "sun"}`,
        );
      }
    };

    let current = localStorage.getItem("theme");
    if (!current) {
      current = "dark";
      localStorage.setItem("theme", current);
    }
    applyTheme(current);

    if (toggle) {
      toggle.addEventListener("click", (e) => {
        e.preventDefault();
        current = current === "light" ? "dark" : "light";
        localStorage.setItem("theme", current);
        applyTheme(current);
      });
    }
  });
}
