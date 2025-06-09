import { fetchJson } from "./fetch_utils.js";

export function initDiscoveryToggle() {
  document.addEventListener("DOMContentLoaded", () => {
    const stopBtn = document.getElementById("stop-discovery");
    const statusSpan = document.getElementById("discovery-bg-status");
    const statusIcon = document.getElementById("discovery-bg-icon");
    let iconBase = "";
    if (statusIcon) {
      const useEl = statusIcon.querySelector("use");
      if (useEl) {
        iconBase = useEl.getAttribute("href").split("#")[0];
      }
    }
    if (!statusSpan) return;

    const minutes = (s) => `${Math.round(s / 60)}m`;
    const formatStatus = (d) => {
      let text = d.status;
      if (d.running_for) {
        text += ` (${minutes(d.running_for)})`;
      } else if (Number.isFinite(d.age) && d.status !== "none") {
        text += ` (${minutes(d.age)} ago)`;
      }
      if (d.next_run_in) {
        text += `, next in ${minutes(d.next_run_in)}`;
      }
      return text;
    };

    const updateIcon = (d) => {
      if (!statusIcon) return;
      const useEl = statusIcon.querySelector("use");
      const colorMap = {
        none: "grey",
        running: "orange",
        ready: "green",
        error: "red",
        stale: "grey",
      };
      statusIcon.style.color = colorMap[d.status] || "grey";
      if (useEl) {
        let symbol = "search";
        if (d.status === "ready") symbol = "check";
        if (d.status === "error") symbol = "alert";
        useEl.setAttribute("href", `${iconBase}#${symbol}`);
      }
    };

    if (stopBtn) {
      stopBtn.addEventListener("click", async () => {
        const confirmStop = confirm(
          "Are you sure you want to stop background discovery?",
        );
        if (!confirmStop) return;
        try {
          const data = await fetchJson("/toggle_discovery", { method: "POST" });
          statusSpan.textContent = formatStatus(data);
          updateIcon(data);
          stopBtn.style.display =
            data.status === "running" ? "inline-block" : "none";
        } catch (err) {
          statusSpan.textContent = "error";
          if (statusIcon) statusIcon.style.color = "red";
          alert("Unable to stop discovery.");
        }
      });
    }

    const refreshStatus = () =>
      fetchJson("/discovery_status")
        .then((data) => {
          statusSpan.textContent = formatStatus(data);
          updateIcon(data);
          if (stopBtn) {
            stopBtn.style.display =
              data.status === "running" ? "inline-block" : "none";
          }
        })
        .catch(() => {
          statusSpan.textContent = "error";
          if (statusIcon) statusIcon.style.color = "red";
        });

    refreshStatus();
    setInterval(refreshStatus, 30000);
  });
}
