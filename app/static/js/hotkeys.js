export function initHotkeys() {
  document.addEventListener("DOMContentLoaded", () => {
    const modal = document.getElementById("hotkeys-modal");
    if (!modal) return;
    const show = () => {
      modal.style.display = "block";
    };
    const hide = () => {
      modal.style.display = "none";
    };
    document.addEventListener("keydown", (e) => {
      const tag = e.target.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || e.target.isContentEditable)
        return;
      if (e.key === "?") {
        show();
      } else if (e.key === "Escape") {
        hide();
      }
    });
    modal.addEventListener("click", (e) => {
      if (e.target === modal) hide();
    });
  });
}
