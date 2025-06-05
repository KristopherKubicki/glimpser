export function initSettingsSearch() {
  document.addEventListener("DOMContentLoaded", () => {
    const headers = document.querySelectorAll(".settings-table th.searchable");
    const container = document.getElementById("settings-search");
    const input = document.getElementById("search-input");
    if (!headers.length || !container || !input) return;

    let column = 0;

    const filterRows = () => {
      const term = input.value.toLowerCase();
      const rows = document.querySelectorAll(".settings-table tbody tr");
      rows.forEach((row) => {
        const cell = row.cells[column];
        const text = cell.textContent.toLowerCase();
        row.style.display = text.includes(term) ? "" : "none";
      });
    };

    headers.forEach((th, idx) => {
      th.addEventListener("click", () => {
        column = idx;
        input.value = "";
        filterRows();
        container.classList.remove("hidden");
        input.focus();
      });
    });

    input.addEventListener("input", filterRows);
  });
}
