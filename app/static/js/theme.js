export function initThemeToggle() {
  document.addEventListener("DOMContentLoaded", () => {
    const toggle = document.getElementById("theme-toggle");
    const useEl = toggle?.querySelector("use");
    const sprite = useEl ? useEl.getAttribute("href").split("#")[0] : "";

    const applyContrastFromStorage = () => {
      const mode = localStorage.getItem("contrast") || "normal";
      document.body.classList.toggle("high-contrast-mode", mode === "high");
    };

    const applyTheme = (theme) => {
      document.body.classList.toggle("light-mode", theme === "light");
      document.body.classList.toggle("dark-mode", theme === "dark");
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
    applyContrastFromStorage();

    if (toggle) {
      toggle.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        current = current === "light" ? "dark" : "light";
        localStorage.setItem("theme", current);
        applyTheme(current);
        applyContrastFromStorage();
        document.querySelector('.tab-link[data-tab="General-tab"]')?.click();
      });
    }
  });
}

export function initContrastToggle() {
  document.addEventListener("DOMContentLoaded", () => {
    const toggle = document.getElementById("contrast-toggle");
    const applyContrast = (mode) => {
      document.body.classList.toggle("high-contrast-mode", mode === "high");
    };

    let current = localStorage.getItem("contrast") || "normal";
    applyContrast(current);

    toggle?.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      current = current === "high" ? "normal" : "high";
      localStorage.setItem("contrast", current);
      applyContrast(current);
    });
  });
}
