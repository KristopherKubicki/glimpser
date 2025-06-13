export function initTabs() {
  document.addEventListener("DOMContentLoaded", () => {
    const tabs = document.querySelectorAll(".tab-link");
    const contents = document.querySelectorAll(".tab-content");
    const addContainer = document.getElementById("add-setting-container");
    const storageKey = `lastTab:${window.location.pathname}`;
    const persist = window.location.pathname !== "/captions";
    if (!tabs.length) return;

    tabs.forEach((tab) => {
      tab.addEventListener("click", () => {
        const target = tab.dataset.tab;
        if (!target) return;
        tabs.forEach((t) => t.classList.remove("active"));
        contents.forEach((c) => c.classList.remove("active"));
        tab.classList.add("active");
        document.getElementById(target)?.classList.add("active");
        if (persist) {
          try {
            localStorage.setItem(storageKey, target);
          } catch {
            /* ignore */
          }
        }
        if (addContainer) {
          if (target === "Other-tab") {
            addContainer.classList.remove("hidden");
          } else {
            addContainer.classList.add("hidden");
          }
        }
      });
    });

    const params = new URLSearchParams(window.location.search);
    const tab =
      persist && (params.get("tab") || localStorage.getItem(storageKey));
    if (tab) {
      const btn = document.querySelector(`.tab-link[data-tab="${tab}"]`);
      btn?.click();
      if (params.get("tab")) {
        history.replaceState(null, "", window.location.pathname);
      }
    }
  });
}
