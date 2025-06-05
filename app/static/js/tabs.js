export function initTabs() {
  document.addEventListener("DOMContentLoaded", () => {
    const tabs = document.querySelectorAll(".tab-link");
    const contents = document.querySelectorAll(".tab-content");
    const addContainer = document.getElementById("add-setting-container");
    if (!tabs.length) return;

    tabs.forEach((tab) => {
      tab.addEventListener("click", () => {
        const target = tab.dataset.tab;
        tabs.forEach((t) => t.classList.remove("active"));
        contents.forEach((c) => c.classList.remove("active"));
        tab.classList.add("active");
        document.getElementById(target)?.classList.add("active");
        if (addContainer) {
          if (target === "Other-tab") {
            addContainer.classList.remove("hidden");
          } else {
            addContainer.classList.add("hidden");
          }
        }
      });
    });
  });
}
