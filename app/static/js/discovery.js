import { fetchJson } from "./fetch_utils.js";

export function initDiscoveryToggle() {
  document.addEventListener("DOMContentLoaded", () => {
    const stopBtn = document.getElementById("stop-discovery");
    const statusSpan = document.getElementById("discovery-bg-status");
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

    if (stopBtn) {
      stopBtn.addEventListener("click", async () => {
        const confirmStop = confirm(
          "Are you sure you want to stop background discovery?",
        );
        if (!confirmStop) return;
        try {
          const data = await fetchJson("/toggle_discovery", { method: "POST" });
          statusSpan.textContent = formatStatus(data);
          stopBtn.style.display =
            data.status === "running" ? "inline-block" : "none";
        } catch (err) {
          statusSpan.textContent = "error";
          alert("Unable to stop discovery.");
        }
      });
    }

    fetchJson("/discovery_status")
      .then((data) => {
        statusSpan.textContent = formatStatus(data);
        if (stopBtn) {
          stopBtn.style.display =
            data.status === "running" ? "inline-block" : "none";
        }
      })
      .catch(() => {
        statusSpan.textContent = "error";
      });
  });
}

export function initDiscoveryPage() {
  document.addEventListener("DOMContentLoaded", () => {
    const button = document.getElementById("discover-btn");
    const msg = document.getElementById("discover-message");
    const progress = document.getElementById("discover-progress");
    const body = document.getElementById("discover-body");
    const exportJson = document.getElementById("export-json");
    const exportCsv = document.getElementById("export-csv");

    const renderInfo = (info) => {
      if (!info) return "";
      const pieces = [];
      if (info.name) pieces.push(info.name);
      if (info.xaddr) pieces.push(info.xaddr);
      if (info.path) pieces.push(info.path);
      if (info.sdp) pieces.push("SDP available");
      Object.entries(info).forEach(([k, v]) => {
        if (!["name", "xaddr", "path", "sdp", "mac", "manufacturer"].includes(k)) {
          pieces.push(`${k}: ${v}`);
        }
      });
      return pieces.join(" ");
    };

    let results = [];
    if (button) {
      button.addEventListener("click", async () => {
        msg.textContent = "Searching...";
        try {
          const res = await fetch("/discovery_status");
          const data = await res.json();
          if (data.status !== "running") {
            await fetch("/toggle_discovery", { method: "POST" });
          }
        } catch (e) {
          console.warn("Unable to start background discovery", e);
        }
        progress.style.display = "inline";
        progress.value = 0;
        body.innerHTML = "";
        results = [];
        const cidr = document.getElementById("cidr-input").value.trim();
        const url =
          cidr ? `/discover/scan_stream?cidr=${encodeURIComponent(cidr)}` : "/discover/scan_stream";
        const source = new EventSource(url);
        const known = new Set();
        const addRow = (cam) => {
          const key = `${cam.ip}-${cam.protocol}-${cam.port}`;
          if (known.has(key)) return;
          known.add(key);
          results.push(cam);
          const tr = document.createElement("tr");
          tr.innerHTML = `
              <td>${cam.ip}</td>
              <td>${cam.protocol}</td>
              <td>${cam.port}</td>
              <td>${cam.info.mac || ""}</td>
              <td>${cam.info.manufacturer || ""}</td>
              <td>${renderInfo(cam.info)}</td>
              <td>
                  <form action="/discover/add" method="post">
                      <input type="hidden" name="ip" value="${cam.ip}">
                      <input type="hidden" name="protocol" value="${cam.protocol}">
                      <input type="hidden" name="port" value="${cam.port}">
                      ${cam.url ? `<input type="hidden" name="url" value="${cam.url}">` : ""}
                      <input type="hidden" name="name" value="${cam.ip}">
                      <button type="submit" title="Add this camera">Add</button>
                  </form>
              </td>`;
          body.appendChild(tr);
        };
        let plan = [];
        source.onmessage = (event) => {
          const data = JSON.parse(event.data);
          if (data.total) {
            progress.max = 100;
            progress.value = 0;
            plan = data.stages || [];
            if (data.subnets) {
              msg.textContent = `Scanning networks: ${data.subnets.join(", ")}. Plan: ${plan.join(", ")}`;
            }
            return;
          }
          if (data.done) {
            msg.textContent = `Found ${known.size} cameras.`;
            progress.style.display = "none";
            source.close();
            return;
          }
          if (typeof data.progress === "number") {
            progress.value = data.progress;
          } else {
            progress.value += 1;
          }
          if (plan.length && plan[0] === data.stage) {
            plan.shift();
          }
          const eta = data.eta ? ` ~${Math.round(data.eta)}s left` : "";
          msg.textContent =
            `Scanning ${data.stage} (${data.count} found)...` +
            (plan.length ? ` Next: ${plan[0]}` : "") +
            eta;
          if (data.cameras) {
            data.cameras.forEach(addRow);
          }
        };
        source.onerror = (e) => {
          console.error("Discovery error", e);
          msg.textContent = "Error discovering cameras";
          progress.style.display = "none";
          source.close();
        };
      });
    }

    const exportData = (fmt) => {
      fetch(`/discover/export?format=${fmt}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(results),
      })
        .then((r) => r.blob())
        .then((blob) => {
          const url = URL.createObjectURL(blob);
          const a = document.createElement("a");
          a.href = url;
          a.download = fmt === "csv" ? "discovery.csv" : "discovery.json";
          document.body.appendChild(a);
          a.click();
          a.remove();
          URL.revokeObjectURL(url);
        });
    };
    if (exportJson) exportJson.addEventListener("click", () => exportData("json"));
    if (exportCsv) exportCsv.addEventListener("click", () => exportData("csv"));
  });
}
