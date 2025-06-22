export function initKeyVisibility() {
  document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll(".toggle-key-visibility").forEach((btn) => {
      btn.addEventListener("click", () => {
        const target = btn.dataset.input;
        const sprite = btn.dataset.sprite;
        const input = document.getElementById(target);
        if (!input) return;
        const useEl = btn.querySelector("use");
        const showing = input.type === "text";
        input.type = showing ? "password" : "text";
        if (useEl && sprite) {
          useEl.setAttribute(
            "href",
            `${sprite}#${showing ? "eye" : "eye-off"}`,
          );
        }
      });
    });
  });
}
