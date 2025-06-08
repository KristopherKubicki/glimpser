import { setupTableSorting } from "./templates.js";

export function groupSmallValues(rows, limit = 15) {
  if (rows.length <= limit) return rows;
  const sorted = [...rows].sort((a, b) => a.cost - b.cost);
  const bottom = sorted.slice(0, limit);
  const other = bottom.reduce(
    (acc, r) => {
      acc.tokens += r.tokens;
      acc.cost += r.cost;
      return acc;
    },
    { name: "Other", tokens: 0, cost: 0 },
  );
  const remaining = sorted.slice(limit).sort((a, b) => b.cost - a.cost);
  return [...remaining, other];
}

export function initCosts() {
  document.addEventListener("DOMContentLoaded", () => {
    const dataEl = document.getElementById("cost-data");
    if (!dataEl) return;
    const range = document.getElementById("cost-range");
    const label = document.getElementById("cost-range-label");
    const tbody = document.querySelector("#cost-table tbody");
    const ctx = document.getElementById("costChart");
    let chart;

    const render = (rows) => {
      tbody.innerHTML = "";
      for (const row of rows) {
        const tr = document.createElement("tr");
        tr.innerHTML = `<td>${row.name}</td><td data-value="${row.tokens}">${row.tokens}</td><td data-value="${row.cost}">$${row.cost.toFixed(2)}</td>`;
        tbody.appendChild(tr);
      }
      if (!ctx) return;
      const grouped = groupSmallValues(rows);
      const labels = grouped.map((r) => r.name);
      const values = grouped.map((r) => r.cost);
      const bg = labels.map((_, i) => `hsl(${(i * 60) % 360},70%,60%)`);
      const chartData = {
        labels,
        datasets: [{ data: values, backgroundColor: bg }],
      };
      if (chart) {
        chart.data = chartData;
        chart.update();
      } else {
        chart = new Chart(ctx, { type: "pie", data: chartData });
      }
    };

    const fetchData = async () => {
      if (!range) {
        render(JSON.parse(dataEl.textContent));
        return;
      }
      const days = parseInt(range.value, 10);
      const end = new Date().toISOString().slice(0, 10);
      const start = new Date(Date.now() - days * 86400000)
        .toISOString()
        .slice(0, 10);
      const resp = await fetch(
        `/api/llm_cost_summary?start=${start}&end=${end}`,
      );
      const data = await resp.json();
      const rows = Object.entries(data).map(([name, info]) => ({
        name,
        tokens: info.tokens,
        cost: parseFloat(info.cost.replace("$", "")),
      }));
      render(rows);
    };

    range?.addEventListener("input", () => {
      if (label) label.textContent = `Last ${range.value} days`;
    });
    range?.addEventListener("change", fetchData);

    setupTableSorting("cost-table");
    fetchData();
  });
}

export function initCostSummary(startTime) {
  document.addEventListener("DOMContentLoaded", () => {
    const startInput = document.getElementById("start-date");
    const endInput = document.getElementById("end-date");
    const loadBtn = document.getElementById("load-cost");
    const sinceBtn = document.getElementById("since-restart");
    const tbody = document.querySelector("#cost-table tbody");
    const ctx = document.getElementById("costChart");
    if (!startInput || !endInput || !loadBtn || !tbody) return;
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
      const bg = labels.map((_, i) => `hsl(${(i * 60) % 360},70%,60%)`);
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
        chart = new Chart(ctx, { type: "pie", data: chartData });
      }
    };

    const loadData = async () => {
      const s = startInput.value;
      const e = endInput.value;
      const resp = await fetch(`/api/llm_cost_summary?start=${s}&end=${e}`);
      const data = await resp.json();
      render(data);
    };

    loadBtn.addEventListener("click", loadData);
    sinceBtn?.addEventListener("click", () => {
      const dt = new Date(startTime * 1000);
      startInput.value = dt.toISOString().slice(0, 10);
      loadData();
    });

    loadData();
  });
}
