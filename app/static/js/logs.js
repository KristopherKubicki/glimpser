import { attemptAutoLogin } from "./login.js";

export function updateTable(logs) {
  const tbody = document.querySelector("#log-table tbody");
  if (!tbody) return;
  tbody.innerHTML = "";
  logs.forEach((log) => {
    const row = document.createElement("tr");

    const timestampCell = document.createElement("td");
    timestampCell.dataset.label = "Timestamp";
    timestampCell.textContent = log.timestamp;

    const levelCell = document.createElement("td");
    levelCell.dataset.label = "Level";
    levelCell.textContent = log.level;

    const sourceCell = document.createElement("td");
    sourceCell.dataset.label = "Source";
    sourceCell.textContent = log.source;

    const messageCell = document.createElement("td");
    messageCell.dataset.label = "Message";
    // Use textContent to avoid interpreting HTML in log messages
    messageCell.textContent = log.message;

    row.append(timestampCell, levelCell, sourceCell, messageCell);

    tbody.appendChild(row);
  });
}

function debounce(fn, delay) {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), delay);
  };
}

function logEventSourceError(src, err) {
  const states = ["CONNECTING", "OPEN", "CLOSED"];
  const state = states[src.readyState] || `unknown (${src.readyState})`;
  console.error(`EventSource failed (state: ${state}):`, err);
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
        const data = JSON.parse(event.data);
        if (data.error === "unauthorized") {
          attemptAutoLogin().then((ok) => {
            if (ok) startEventStream();
          });
          return;
        }
        updateTable(data);
      };

      eventSource.onerror = (error) => {
        logEventSourceError(eventSource, error);
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

    const debouncedStart = debounce(startEventStream, 300);
    searchInput.addEventListener("input", debouncedStart);

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
