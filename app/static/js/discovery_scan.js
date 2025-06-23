export function initDiscoveryScan() {
  document.addEventListener("DOMContentLoaded", () => {
    const page = document.querySelector(".discovery-page");
    if (!page) return;
    const existingMap = JSON.parse(page.dataset.existingMap || "{}");
    const iconUrl = page.dataset.iconUrl || "/static/icons/sprite.svg";
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
        if (
          !["name", "xaddr", "path", "sdp", "mac", "manufacturer"].includes(k)
        ) {
          pieces.push(`${k}: ${v}`);
        }
      });
      return pieces.join(" ");
    };

    let results = [];
    const updateExportState = () => {
      if (exportJson) exportJson.disabled = results.length === 0;
      if (exportCsv) exportCsv.disabled = results.length === 0;
    };
    updateExportState();

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
        updateExportState();
        const cidr = document.getElementById("cidr-input").value.trim();
        const url = cidr
          ? `/discover/scan_stream?cidr=${encodeURIComponent(cidr)}`
          : "/discover/scan_stream";
        const source = new EventSource(url);
        const known = new Set();
        const addRow = (cam) => {
          const key = cam.ip
            ? `${cam.ip}-${cam.protocol}-${cam.port}`
            : cam.url;
          if (known.has(key)) return;
          known.add(key);
          results.push(cam);
          updateExportState();
          const tr = document.createElement("tr");
          let url = cam.url || `${cam.protocol}://${cam.ip}:${cam.port}`;
          const existing = existingMap[url];
          const action = existing
            ? `<a href="/templates/${existing}" class="btn btn-primary" title="View this camera">View</a>`
            : `<form action="/discover/add" method="post">
                            ${
                              cam.ip
                                ? `<input type="hidden" name="ip" value="${cam.ip}">`
                                : ""
                            }
                            ${
                              cam.protocol
                                ? `<input type="hidden" name="protocol" value="${cam.protocol}">`
                                : ""
                            }
                            ${
                              cam.port
                                ? `<input type="hidden" name="port" value="${cam.port}">`
                                : ""
                            }
                            ${
                              cam.url
                                ? `<input type="hidden" name="url" value="${cam.url}">`
                                : ""
                            }
                            <input type="hidden" name="name" value="${cam.name || cam.ip}">
                            <button type="submit" title="Add this camera">Add</button>
                        </form>`;
          let protocol = cam.protocol;
          let port = cam.port;
          if (!cam.ip && cam.url) {
            try {
              const p = new URL(cam.url);
              protocol = protocol || p.protocol.replace(":", "");
              port = port || p.port || (p.protocol === "https:" ? "443" : "80");
            } catch {}
          }
          const info = renderInfo(
            cam.info || {
              name: cam.name,
              category: cam.category,
              notes: cam.notes,
            },
          );
          tr.innerHTML = `
                    <td>${cam.ip || ""}</td>
                    <td>${protocol || ""}</td>
                    <td>${port || ""}</td>
                    <td>${(cam.info && cam.info.mac) || ""}</td>
                    <td>${(cam.info && cam.info.manufacturer) || ""}</td>
                    <td><svg class="camera-icon" width="12" height="12" aria-hidden="true"><use href="${iconUrl}#camera"></use></svg>
                    ${info ? `<span class="info-icon" title="${info}">ℹ️</span>` : ""}</td>
                    <td>${action}</td>`;
          body.appendChild(tr);
        };
        let plan = [];
        source.onmessage = (event) => {
          const data = JSON.parse(event.data);
          if (data.error) {
            console.error("Discovery error", data.error);
            msg.textContent = `Error discovering cameras: ${data.error}`;
            progress.style.display = "none";
            source.close();
            return;
          }
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
          let text = "Error discovering cameras";
          if (e && e.message) {
            text += `: ${e.message}`;
          }
          msg.textContent = text;
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
    if (exportJson)
      exportJson.addEventListener("click", () => exportData("json"));
    if (exportCsv) exportCsv.addEventListener("click", () => exportData("csv"));
  });
}
