import { fetchJson } from "./fetch_utils.js";

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
          schedulerStatus.textContent = data.status;
          toggleSchedulerButton.textContent =
            data.status === "running" ? "Stop Scheduler" : "Start Scheduler";
        } catch (error) {
          schedulerStatus.textContent = "Error occurred";
          alert("Unable to toggle scheduler.");
        }
      });

      fetchJson("/scheduler_status")
        .then((data) => {
          schedulerStatus.textContent = data.status;
          toggleSchedulerButton.textContent =
            data.status === "running" ? "Stop Scheduler" : "Start Scheduler";
        })
        .catch(() => {
          schedulerStatus.textContent = "Error occurred";
        });
    }
  });
}
