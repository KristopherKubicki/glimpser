import { fetchJson } from "./fetch_utils.js";

function setStatus(el, status) {
  if (!el) return;
  el.classList.remove("ok", "slow", "error");
  el.classList.add(status);
}

function updateStatusText(el, status) {
  el.textContent = status;
  const map = { running: "ok", stopped: "error", error: "error" };
  setStatus(el, map[status] || "error");
}

export function initSchedulerToggle() {
  document.addEventListener("DOMContentLoaded", () => {
    const toggleSchedulerButton = document.getElementById("toggle-scheduler");
    const schedulerStatus = document.getElementById("scheduler-status");
    if (toggleSchedulerButton && schedulerStatus) {
      toggleSchedulerButton.addEventListener("click", async () => {
        const shouldToggle = confirm(
          `Are you sure you want to ${
            toggleSchedulerButton.textContent.includes("Stop")
              ? "stop"
              : "start"
          } the scheduler?`,
        );
        if (!shouldToggle) return;
        try {
          const data = await fetchJson("/toggle_scheduler", { method: "POST" });
          updateStatusText(schedulerStatus, data.status);
          toggleSchedulerButton.textContent =
            data.status === "running" ? "Stop Scheduler" : "Start Scheduler";
        } catch (error) {
          updateStatusText(schedulerStatus, "error");
          alert("Unable to toggle scheduler.");
        }
      });

      fetchJson("/scheduler_status")
        .then((data) => {
          updateStatusText(schedulerStatus, data.status);
          toggleSchedulerButton.textContent =
            data.status === "running" ? "Stop Scheduler" : "Start Scheduler";
        })
        .catch(() => {
          updateStatusText(schedulerStatus, "error");
        });
    }
  });
}
