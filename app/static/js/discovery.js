import { fetchJson } from "./fetch_utils.js";
import { setupTableSorting } from "./templates.js";

export function initDiscoveryToggle() {
  document.addEventListener("DOMContentLoaded", () => {
    const stopBtn = document.getElementById("stop-discovery");
    const statusSpan = document.getElementById("discovery-bg-status");
    const statusIcon = document.getElementById("discovery-bg-icon");
    if (!statusSpan) return;

    const setStatusClass = (status) => {
      if (!statusIcon) return;
      statusIcon.classList.remove("ok", "slow", "error");
      const map = {
        running: "slow",
        ready: "ok",
        stale: "slow",
        error: "error",
      };
      const cls = map[status];
      if (cls) statusIcon.classList.add(cls);
    };

    const minutes = (s) => `${Math.round(s / 60)}m`;
    const formatStatus = (d) => {
      const statusText = d.status === "none" ? "disabled" : d.status;
      let text = statusText;
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

    if (stopBtn) {
      stopBtn.addEventListener("click", async () => {
        const confirmStop = confirm(
          "Are you sure you want to stop background discovery?",
        );
        if (!confirmStop) return;
        try {
          const data = await fetchJson("/toggle_discovery", { method: "POST" });
          statusSpan.textContent = formatStatus(data);
          setStatusClass(data.status);
          stopBtn.style.display =
            data.status === "running" ? "inline-block" : "none";
        } catch (err) {
          statusSpan.textContent = "error";
          setStatusClass("error");
          alert("Unable to stop discovery.");
        }
      });
    }

    const refreshStatus = () =>
      fetchJson("/discovery_status")
        .then((data) => {
          statusSpan.textContent = formatStatus(data);
          setStatusClass(data.status);
          if (stopBtn) {
            stopBtn.style.display =
              data.status === "running" ? "inline-block" : "none";
          }
        })
        .catch(() => {
          statusSpan.textContent = "error";
          setStatusClass("error");
        });

    refreshStatus();
    setInterval(refreshStatus, 30000);
  });
}

export function initSubnetInput() {
  document.addEventListener("DOMContentLoaded", async () => {
    const input = document.getElementById("cidr-input");
    if (!input) return;

    let datalist = document.getElementById("cidr-options");
    if (!datalist) {
      datalist = document.createElement("datalist");
      datalist.id = "cidr-options";
      if (input.parentNode) {
        input.parentNode.insertBefore(datalist, input.nextSibling);
      }
    }
    input.setAttribute("list", "cidr-options");

    try {
      const res = await fetch("/discover/subnets");
      const nets = await res.json();
      datalist.innerHTML = nets
        .map((n) => `<option value="${n}"></option>`)
        .join("");
    } catch (err) {
      console.warn("subnet fetch failed", err);
    }

    const isValidCidr = (value) => {
      if (!/^\d{1,3}(?:\.\d{1,3}){3}\/\d{1,2}$/.test(value)) return false;
      const [ip, prefix] = value.split("/");
      if (ip.split(".").some((o) => +o > 255)) return false;
      const p = parseInt(prefix, 10);
      return p >= 0 && p <= 32;
    };

    input.addEventListener("input", () => {
      const val = input.value.trim();
      if (val && !isValidCidr(val)) {
        input.setCustomValidity("Invalid CIDR");
      } else {
        input.setCustomValidity("");
      }
    });
  });
}

export function initDiscoveryTable() {
  document.addEventListener("DOMContentLoaded", () => {
    if (document.getElementById("discover-table")) {
      setupTableSorting("discover-table");
    }
  });
}
