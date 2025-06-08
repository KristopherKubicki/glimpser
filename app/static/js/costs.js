import { setupTableSorting } from "./templates.js";

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
      const labels = [];
      const values = [];
      for (const row of rows) {
        const tr = document.createElement("tr");
        tr.innerHTML = `<td>${row.name}</td><td data-value="${row.tokens}">${row.tokens}</td><td data-value="${row.cost}">$${row.cost.toFixed(2)}</td>`;
        tbody.appendChild(tr);
        labels.push(row.name);
        values.push(row.cost);
      }
      if (!ctx) return;
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
      const labels = [];
      const values = [];
      for (const name in data) {
        const info = data[name];
        const row = document.createElement("tr");
        row.innerHTML = `<td>${name}</td><td>${info.cost}</td>`;
        tbody.appendChild(row);
        labels.push(name);
        values.push(parseFloat(info.cost.replace("$", "")));
      }
      if (!ctx) return;
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
