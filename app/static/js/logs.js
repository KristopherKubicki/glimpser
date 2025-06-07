function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = String(str);
  return div.innerHTML;
}

export function updateTable(logs) {
  const tbody = document.querySelector("#log-table tbody");
  if (!tbody) return;
  tbody.innerHTML = "";
  logs.forEach((log) => {
    const row = document.createElement("tr");
    row.innerHTML = `
            <td data-label="Timestamp">${escapeHtml(log.timestamp)}</td>
            <td data-label="Level">${escapeHtml(log.level)}</td>
            <td data-label="Source">${escapeHtml(log.source)}</td>
            <td data-label="Message">${escapeHtml(log.message)}</td>
        `;
    tbody.appendChild(row);
  });
}

export function initLogs() {
  document.addEventListener("DOMContentLoaded", () => {
    const form = document.getElementById("log-filter-form");
    const table = document.getElementById("log-table");
    const searchInput = document.getElementById("search-input");
    const levelSelect = document.getElementById("level-select");
    const status = document.getElementById("log-connection-status");

    let eventSource;
    let reconnectTimer;

    function startEventStream() {
      if (eventSource) {
        eventSource.close();
      }

      const formData = new FormData(form);
      const searchParams = new URLSearchParams(formData);
      eventSource = new EventSource(`/stream_logs?${searchParams.toString()}`);
      if (status) status.classList.add("hidden");

      eventSource.onopen = () => {
        if (status) status.classList.add("hidden");
      };

      eventSource.onmessage = (event) => {
        const logs = JSON.parse(event.data);
        updateTable(logs);
      };

      eventSource.onerror = (error) => {
        console.error("EventSource failed:", error);
        if (status) {
          status.textContent = "Connection lost. Reconnecting...";
          status.classList.remove("hidden");
        }
        eventSource.close();
        clearTimeout(reconnectTimer);
        reconnectTimer = setTimeout(startEventStream, 3000);
      };
    }

    form.addEventListener("submit", (e) => {
      e.preventDefault();
      startEventStream();
    });

    searchInput.addEventListener("input", () => {
      startEventStream();
    });

    levelSelect.addEventListener("change", () => {
      startEventStream();
    });

    // Start the initial event stream
    startEventStream();

    // expose for tests
    window.__startLogStream = startEventStream;
  });
}

initLogs();

// Expose for legacy scripts that include this file via <script> tag
window.updateTable = updateTable;
