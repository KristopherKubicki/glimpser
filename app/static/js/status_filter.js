let activeStatus = null;

export function applyStatusFilter() {
  document
    .querySelectorAll("#template-list .video-container")
    .forEach((box) => {
      const wrapper = box.closest(".templateDiv");
      if (!wrapper) return;
      const isRecent = box.classList.contains("recent-screenshot");
      const isError = box.classList.contains("template-error");
      let show = true;
      if (activeStatus === "recent") show = isRecent;
      else if (activeStatus === "error") show = isError;
      wrapper.style.display = show ? "" : "none";
    });
}

export function updateStatusCounts() {
  const legend = document.getElementById("status-legend");
  if (!legend) return;
  const recent = document.querySelectorAll(
    "#template-list .video-container.recent-screenshot",
  ).length;
  const error = document.querySelectorAll(
    "#template-list .video-container.template-error",
  ).length;
  legend
    .querySelector('[data-status="recent"]')
    ?.classList.toggle("disabled", recent === 0);
  legend
    .querySelector('[data-status="error"]')
    ?.classList.toggle("disabled", error === 0);
}

export function setupStatusFilter() {
  document.addEventListener("DOMContentLoaded", () => {
    const legend = document.getElementById("status-legend");
    if (!legend) return;
    legend.querySelectorAll(".status-item").forEach((item) => {
      item.dataset.status ||= item.textContent.trim().toLowerCase();
      item.addEventListener("click", () => {
        if (item.classList.contains("disabled")) return;
        const status = item.dataset.status;
        if (activeStatus === status) {
          activeStatus = null;
          item.classList.remove("active");
        } else {
          activeStatus = status;
          legend
            .querySelectorAll(".status-item")
            .forEach((i) => i.classList.toggle("active", i === item));
        }
        applyStatusFilter();
      });
    });
    updateStatusCounts();
    window.addEventListener("templatesLoaded", updateStatusCounts);
  });
}
