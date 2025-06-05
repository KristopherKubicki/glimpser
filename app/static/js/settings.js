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

export function initEnumFields() {
  document.addEventListener("DOMContentLoaded", () => {
    const selects = document.querySelectorAll("select[data-other-target]");
    selects.forEach((sel) => {
      const targetId = sel.getAttribute("data-other-target");
      const input = document.getElementById(targetId);
      if (!input) return;
      const toggle = () => {
        if (sel.value === "__other__") {
          input.classList.remove("hidden");
        } else {
          input.classList.add("hidden");
        }
      };
      sel.addEventListener("change", toggle);
      toggle();
    });
  });
}
