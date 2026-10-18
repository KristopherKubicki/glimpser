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
    let saved = null;
    if (persist) {
      try {
        saved = localStorage.getItem(storageKey);
      } catch {
        /* optional */
      }
    }
    const tab = params.get("tab") || saved;
    if (tab) {
      const btn = Array.from(tabs).find((button) => button.dataset.tab === tab);
      btn?.click();
      if (params.get("tab")) {
        params.delete("tab");
        const remaining = params.toString();
        history.replaceState(
          null,
          "",
          window.location.pathname + (remaining ? `?${remaining}` : ""),
        );
      }
    }
  });
}
