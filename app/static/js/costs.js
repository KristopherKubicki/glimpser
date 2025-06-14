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
    const startSlider = document.getElementById("cost-start");
    const endSlider = document.getElementById("cost-end");
    const startLabel = document.getElementById("cost-start-label");
    const endLabel = document.getElementById("cost-end-label");
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

    const base = new Date();
    base.setMonth(base.getMonth() - 6);

    const toDate = (val) => {
      const d = new Date(base.getTime());
      d.setDate(base.getDate() + parseInt(val, 10));
      return d;
    };

    const fetchData = async () => {
      if (!startSlider || !endSlider) {
        rowsData = JSON.parse(dataEl.textContent);
        render();
        return;
      }
      const params = [];
      const start = toDate(startSlider.value);
      const end = toDate(endSlider.value);
      params.push(`start=${start.toISOString().slice(0, 10)}`);
      params.push(`end=${end.toISOString().slice(0, 10)}`);
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

    const updateLabels = () => {
      if (startLabel)
        startLabel.textContent = toDate(startSlider.value)
          .toISOString()
          .slice(0, 10);
      if (endLabel)
        endLabel.textContent = toDate(endSlider.value)
          .toISOString()
          .slice(0, 10);
    };
    startSlider?.addEventListener("input", () => {
      if (parseInt(startSlider.value, 10) > parseInt(endSlider.value, 10)) {
        startSlider.value = endSlider.value;
      }
      updateLabels();
      fetchData();
    });
    endSlider?.addEventListener("input", () => {
      if (parseInt(endSlider.value, 10) < parseInt(startSlider.value, 10)) {
        endSlider.value = startSlider.value;
      }
      updateLabels();
      fetchData();
    });
    groupSelect?.addEventListener("change", fetchData);

    topSlider?.addEventListener("input", () => {
      if (topLabel) topLabel.textContent = `Top ${topSlider.value}`;
      render();
    });

    setupTableSorting("cost-table");
    loadGroups();
    if (startSlider && endSlider) {
      updateLabels();
    }
    fetchData();
  });
}

export function initCostSummary(startTime) {
  document.addEventListener("DOMContentLoaded", () => {
    const startSlider = document.getElementById("cost-start");
    const endSlider = document.getElementById("cost-end");
    const startLabel = document.getElementById("cost-start-label");
    const endLabel = document.getElementById("cost-end-label");
    const groupSelect = document.getElementById("cost-group");
    const loadBtn = document.getElementById("load-cost");
    const sinceBtn = document.getElementById("since-restart");
    const tbody = document.querySelector("#cost-table tbody");
    const ctx = document.getElementById("costChart");
    if (!startSlider || !endSlider || !loadBtn || !tbody) return;
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

    const base = new Date();
    base.setMonth(base.getMonth() - 6);

    const toDate = (val) => {
      const d = new Date(base.getTime());
      d.setDate(base.getDate() + parseInt(val, 10));
      return d;
    };

    const loadData = async () => {
      const start = toDate(startSlider.value);
      const end = toDate(endSlider.value);
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

    const updateLabels = () => {
      if (startLabel)
        startLabel.textContent = toDate(startSlider.value)
          .toISOString()
          .slice(0, 10);
      if (endLabel)
        endLabel.textContent = toDate(endSlider.value)
          .toISOString()
          .slice(0, 10);
    };

    loadBtn.addEventListener("click", loadData);
    startSlider.addEventListener("input", () => {
      if (parseInt(startSlider.value, 10) > parseInt(endSlider.value, 10)) {
        startSlider.value = endSlider.value;
      }
      updateLabels();
    });
    endSlider.addEventListener("input", () => {
      if (parseInt(endSlider.value, 10) < parseInt(startSlider.value, 10)) {
        endSlider.value = startSlider.value;
      }
      updateLabels();
    });
    groupSelect?.addEventListener("change", loadData);
    sinceBtn?.addEventListener("click", () => {
      const dt = new Date(startTime * 1000);
      const diff = Math.ceil((Date.now() - dt.getTime()) / 86400000);
      const val = Math.min(diff, 180);
      startSlider.value = String(0);
      endSlider.value = String(val);
      updateLabels();
      loadData();
    });

    loadGroups();
    if (startSlider && endSlider) {
      updateLabels();
    }
    loadData();
  });
}
