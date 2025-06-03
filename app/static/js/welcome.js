export function initWelcome() {
  document.addEventListener("DOMContentLoaded", () => {
    const modal = document.getElementById("welcome-modal");
    const closeBtn = document.getElementById("welcome-close");
    const okBtn = document.getElementById("welcome-ok");

    if (!modal) return;

    const hide = () => {
      modal.style.display = "none";
      // Remember dismissal so returning users are not prompted again
      localStorage.setItem("welcomeSeen", "true");
    };

    const maybeShow = (count) => {
      if (count === 0 && !localStorage.getItem("welcomeSeen")) {
        modal.style.display = "block";
      }
    };

    if (closeBtn) closeBtn.addEventListener("click", hide);
    if (okBtn) okBtn.addEventListener("click", hide);

    window.addEventListener("templatesLoaded", (e) => {
      const c = e.detail?.count ?? 0;
      maybeShow(c);
    });
  });
}
