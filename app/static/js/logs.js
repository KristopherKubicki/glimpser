export function updateTable(logs) {
  const tbody = document.querySelector("#log-table tbody");
  if (!tbody) return;
  tbody.innerHTML = "";
  logs.forEach((log) => {
    const row = document.createElement("tr");
    row.innerHTML = `
            <td data-label="Timestamp">${log.timestamp}</td>
            <td data-label="Level">${log.level}</td>
            <td data-label="Source">${log.source}</td>
            <td data-label="Message">${log.message}</td>
        `;
    tbody.appendChild(row);
  });
}

document.addEventListener("DOMContentLoaded", function () {
  const form = document.getElementById("log-filter-form");
  const table = document.getElementById("log-table");
  const searchInput = document.getElementById("search-input");
  const levelSelect = document.getElementById("level-select");

  let eventSource;

  function startEventStream() {
    if (eventSource) {
      eventSource.close();
    }

    const formData = new FormData(form);
    const searchParams = new URLSearchParams(formData);
    eventSource = new EventSource(`/stream_logs?${searchParams.toString()}`);

    eventSource.onmessage = function (event) {
      const logs = JSON.parse(event.data);
      updateTable(logs);
    };

    eventSource.onerror = function (error) {
      console.error("EventSource failed:", error);
      eventSource.close();
    };
  }

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    startEventStream();
  });

  searchInput.addEventListener("input", function () {
    startEventStream();
  });

  levelSelect.addEventListener("change", function () {
    startEventStream();
  });

  // Start the initial event stream
  startEventStream();
});

// Expose for legacy scripts that include this file via <script> tag
window.updateTable = updateTable;
