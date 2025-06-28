export function initSearchShortcut() {
  document.addEventListener("DOMContentLoaded", () => {
    const input = document.getElementById("search-input");
    const container = document.getElementById("search-container");
    if (!input) return;
    const focusSearch = () => {
      if (container) {
        container.classList.remove("fade-out");
        container.style.display = "";
      }
      input.focus();
      input.select();
    };
    document.addEventListener("keydown", (e) => {
      const tag = e.target.tagName;
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "f") {
        if (
          tag !== "INPUT" &&
          tag !== "TEXTAREA" &&
          !e.target.isContentEditable
        ) {
          e.preventDefault();
          focusSearch();
        }
      }
    });
  });
}
