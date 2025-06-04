export function initCaptions() {
  document.addEventListener("DOMContentLoaded", () => {
    const tabs = document.querySelectorAll(".tab-link");
    const contents = document.querySelectorAll(".tab-content");
    if (!tabs.length) return;

    const modal = document.getElementById("update-modal");
    const confirmBtn = document.getElementById("update-confirm");
    const cancelBtn = document.getElementById("update-cancel");
    const closeBtn = document.getElementById("update-close");
    let pending = null;

    const hide = () => {
      if (modal) modal.style.display = "none";
    };

    cancelBtn?.addEventListener("click", hide);
    closeBtn?.addEventListener("click", hide);
    confirmBtn?.addEventListener("click", () => {
      hide();
      if (pending) window.updateTemplate(pending);
    });

    document.getElementById("camera-table")?.addEventListener("click", (e) => {
      const btn = e.target.closest(".update-button");
      if (!btn) return;
      e.preventDefault();
      pending = btn.dataset.template;
      if (modal) {
        modal.style.display = "block";
      } else {
        window.updateTemplate(pending);
      }
    });

    tabs.forEach((tab) => {
      tab.addEventListener("click", () => {
        const target = tab.dataset.tab;
        tabs.forEach((t) => t.classList.remove("active"));
        contents.forEach((c) => c.classList.remove("active"));
        tab.classList.add("active");
        document.getElementById(target)?.classList.add("active");
      });
    });
  });
}
