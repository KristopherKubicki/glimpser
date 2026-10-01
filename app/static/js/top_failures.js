function parseTimestamp(value) {
  if (!value) return null;
  const iso = value.includes("T")
    ? /Z$|[+-]\d{2}:?\d{2}$/.test(value)
      ? value
      : `${value}Z`
    : `${value.replace(" ", "T")}Z`;
  const parsed = new Date(iso);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function initTopFailures() {
  const table = document.getElementById("top-failures");
  if (!table) return;
  const tbody = table.tBodies[0];
  const rows = Array.from(tbody.rows);
  const searchInput = document.getElementById("top-failures-search");
  const reasonSelect = document.getElementById("top-failures-reason");
  const windowSelect = document.getElementById("top-failures-window");
  const countEl = document.getElementById("top-failures-count");

  if (!searchInput || !reasonSelect || !windowSelect || !countEl) return;

  const reasons = new Set();
  rows.forEach((row) => {
    const reason = row.dataset.reason || "";
    if (reason) reasons.add(reason);
  });
  Array.from(reasons)
    .sort((a, b) => a.localeCompare(b))
    .forEach((reason) => {
      const opt = document.createElement("option");
      opt.value = reason;
      opt.textContent = reason;
      reasonSelect.appendChild(opt);
    });

  const updateCount = (visible) => {
    countEl.textContent = `${visible} of ${rows.length}`;
  };

  const applyFilters = () => {
    const term = searchInput.value.trim().toLowerCase();
    const reasonFilter = reasonSelect.value;
    const windowSeconds = parseInt(windowSelect.value || "0", 10);
    const cutoff = windowSeconds ? Date.now() - windowSeconds * 1000 : null;
    let visible = 0;

    rows.forEach((row) => {
      const rowReason = row.dataset.reason || "";
      const rowName = row.dataset.name || "";
      const rowUrl = row.dataset.url || "";
      const text = `${rowName} ${rowReason} ${rowUrl}`.toLowerCase();
      let matches = true;

      if (term && !text.includes(term)) {
        matches = false;
      }
      if (reasonFilter && rowReason !== reasonFilter) {
        matches = false;
      }
      if (cutoff) {
        const lastSeen = parseTimestamp(row.dataset.lastSeen || "");
        if (!lastSeen || lastSeen.getTime() < cutoff) {
          matches = false;
        }
      }

      row.style.display = matches ? "" : "none";
      if (matches) visible += 1;
    });

    updateCount(visible);
  };

  searchInput.addEventListener("input", applyFilters);
  reasonSelect.addEventListener("change", applyFilters);
  windowSelect.addEventListener("change", applyFilters);
  applyFilters();
}

document.addEventListener("DOMContentLoaded", initTopFailures);
