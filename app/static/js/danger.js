export function initDangerToggle() {
  document.addEventListener("DOMContentLoaded", () => {
    const form = document.getElementById("danger-form");
    if (!form) return;
    const modal = document.getElementById("danger-modal");
    const message = document.getElementById("danger-modal-message");
    const confirmBtn = document.getElementById("danger-confirm");
    const cancelBtn = document.getElementById("danger-cancel");
    const closeBtn = document.getElementById("danger-close");

    const hide = () => {
      if (modal) modal.style.display = "none";
    };

    if (cancelBtn) cancelBtn.addEventListener("click", hide);
    if (closeBtn) closeBtn.addEventListener("click", hide);

    form.addEventListener("submit", (e) => {
      e.preventDefault();
      const enable = form.elements["enabled"].checked;
      if (modal && message) {
        message.textContent = enable
          ? "Enable Danger Mode? Glimpser will use your current Chrome session."
          : "Disable Danger Mode? Captures marked as Danger will be skipped.";
        modal.style.display = "block";
      } else {
        form.submit();
      }
    });

    if (confirmBtn) {
      confirmBtn.addEventListener("click", () => {
        hide();
        form.submit();
      });
    }
  });
}
