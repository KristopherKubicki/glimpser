import { setupTableSorting, loadGroups } from "./templates.js";

export function groupSmallValues(rows, limit = 15) {
  if (limit <= 0 || rows.length <= limit) {
    return [...rows].sort((a, b) => b.cost - a.cost);
  }
  const sorted = [...rows].sort((a, b) => a.cost - b.cost);
  const bottom = sorted.slice(0, limit);
  const other = bottom.reduce(
    (acc, r) => {
      acc.tokens += r.tokens;
      acc.cost += r.cost;
      acc.calls += r.calls ?? 0;
      return acc;
    },
    { name: "Other", tokens: 0, cost: 0, calls: 0 },
  );
  const remaining = sorted.slice(limit).sort((a, b) => b.cost - a.cost);
  return [...remaining, other];
}

export function initCosts() {
  document.addEventListener("DOMContentLoaded", () => {
    const dataEl = document.getElementById("cost-data");
    if (!dataEl) return;
    const rangeInput = document.getElementById("cost-range");
    const rangeLabel = document.getElementById("cost-range-label");
    const groupSelect = document.getElementById("cost-group");
    const topSlider = document.getElementById("cost-top");
    const topLabel = document.getElementById("cost-top-label");
    const tbody = document.querySelector("#cost-table tbody");
    const ctx = document.getElementById("costChart");
    let chart;
    let rowsData = [];

    const render = (rows = rowsData) => {
      const top = topSlider ? parseInt(topSlider.value, 10) : 10;
      const limit = rows.length > top ? rows.length - (top - 1) : 0;
      const grouped =
        limit > 0 ? groupSmallValues(rows, limit) : groupSmallValues(rows, 0);
      tbody.innerHTML = "";
      for (const row of grouped) {
        const tr = document.createElement("tr");
        tr.innerHTML = `<td>${row.name}</td><td data-value="${row.calls}">${row.calls}</td><td data-value="${row.tokens}">${row.tokens}</td><td data-value="${row.cost}">$${row.cost.toFixed(2)}</td>`;
        tbody.appendChild(tr);
      }
      if (!ctx) return;
      const labels = grouped.map((r) => r.name);
      const values = grouped.map((r) => r.cost);
      const bg = labels.map((_, i) => `hsl(${(i * 60) % 360},40%,45%)`);
      const chartData = {
        labels,
        datasets: [{ data: values, backgroundColor: bg }],
      };
      if (chart) {
        chart.data = chartData;
        chart.update();
      } else {
        chart = new Chart(ctx, {
          type: "pie",
          data: chartData,
          options: {
            responsive: false,
            plugins: { legend: { display: false } },
          },
        });
      }
    };

    const fetchData = async () => {
      if (!rangeInput) {
        rowsData = JSON.parse(dataEl.textContent);
        render();
        return;
      }
      const params = [];
      if (rangeInput) {
        const days = parseInt(rangeInput.value, 10);
        const end = new Date();
        const start = new Date(Date.now() - days * 86400000);
        params.push(`start=${start.toISOString().slice(0, 10)}`);
        params.push(`end=${end.toISOString().slice(0, 10)}`);
      }
      if (groupSelect && groupSelect.value && groupSelect.value !== "all") {
        params.push(`group=${groupSelect.value}`);
      }
      const url = params.length
        ? `/api/llm_cost_summary?${params.join("&")}`
        : "/api/llm_cost_summary";
      const resp = await fetch(url);
      const data = await resp.json();
      const rows = Object.entries(data).map(([name, info]) => ({
        name,
        calls: info.calls ?? 0,
        tokens: info.tokens,
        cost: parseFloat(info.cost.replace("$", "")),
      }));
      rowsData = rows;
      render();
    };

    rangeInput?.addEventListener("input", () => {
      if (rangeLabel) rangeLabel.textContent = `${rangeInput.value} days`;
      fetchData();
    });
    groupSelect?.addEventListener("change", fetchData);

    topSlider?.addEventListener("input", () => {
      if (topLabel) topLabel.textContent = `Top ${topSlider.value}`;
      render();
    });

    setupTableSorting("cost-table");
    loadGroups();
    if (rangeInput && rangeLabel) {
      rangeLabel.textContent = `${rangeInput.value} days`;
    }
    fetchData();
  });
}

export function initCostSummary(startTime) {
  document.addEventListener("DOMContentLoaded", () => {
    const rangeInput = document.getElementById("cost-range");
    const rangeLabel = document.getElementById("cost-range-label");
    const groupSelect = document.getElementById("cost-group");
    const loadBtn = document.getElementById("load-cost");
    const sinceBtn = document.getElementById("since-restart");
    const tbody = document.querySelector("#cost-table tbody");
    const ctx = document.getElementById("costChart");
    if (!rangeInput || !loadBtn || !tbody) return;
    let chart;

    const render = (data) => {
      tbody.innerHTML = "";
      const rows = [];
      for (const name in data) {
        const info = data[name];
        const row = {
          name,
          tokens: info.tokens ?? 0,
          cost: parseFloat(info.cost.replace("$", "")),
        };
        rows.push(row);
        const tr = document.createElement("tr");
        tr.innerHTML = `<td>${name}</td><td>${info.cost}</td>`;
        tbody.appendChild(tr);
      }
      if (!ctx) return;
      const grouped = groupSmallValues(rows);
      const labels = grouped.map((r) => r.name);
      const values = grouped.map((r) => r.cost);
      const bg = labels.map((_, i) => `hsl(${(i * 60) % 360},40%,45%)`);
      const chartData = {
        labels,
        datasets: [
          {
            data: values,
            backgroundColor: bg,
            borderWidth: 0,
          },
        ],
      };
      if (chart) {
        chart.data = chartData;
        chart.update();
      } else {
        chart = new Chart(ctx, {
          type: "pie",
          data: chartData,
          options: {
            responsive: false,
            plugins: { legend: { display: false } },
          },
        });
      }
    };

    const loadData = async () => {
      const days = parseInt(rangeInput.value, 10);
      const end = new Date();
      const start = new Date(Date.now() - days * 86400000);
      const params = [
        `start=${start.toISOString().slice(0, 10)}`,
        `end=${end.toISOString().slice(0, 10)}`,
      ];
      if (groupSelect && groupSelect.value && groupSelect.value !== "all") {
        params.push(`group=${groupSelect.value}`);
      }
      const resp = await fetch(`/api/llm_cost_summary?${params.join("&")}`);
      const data = await resp.json();
      render(data);
    };

    loadBtn.addEventListener("click", loadData);
    rangeInput.addEventListener("input", () => {
      if (rangeLabel) rangeLabel.textContent = `${rangeInput.value} days`;
    });
    groupSelect?.addEventListener("change", loadData);
    sinceBtn?.addEventListener("click", () => {
      const dt = new Date(startTime * 1000);
      const diff = Math.ceil((Date.now() - dt.getTime()) / 86400000);
      rangeInput.value = String(diff);
      if (rangeLabel) rangeLabel.textContent = `${rangeInput.value} days`;
      loadData();
    });

    loadGroups();
    if (rangeLabel) rangeLabel.textContent = `${rangeInput.value} days`;
    loadData();
  });
}
