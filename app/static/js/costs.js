export function initCosts() {
  document.addEventListener("DOMContentLoaded", () => {
    const dataEl = document.getElementById("cost-data");
    if (!dataEl) return;
    const data = JSON.parse(dataEl.textContent);
    const groupSel = document.getElementById("cost-group");
    const camSel = document.getElementById("cost-camera");
    const tbody = document.querySelector("#cost-table tbody");
    const ctx = document.getElementById("costChart");
    let chart;

    const filterData = () => {
      const g = groupSel.value;
      const c = camSel.value;
      return data.filter((d) => (!g || d.group === g) && (!c || d.name === c));
    };

    const renderTable = () => {
      tbody.innerHTML = "";
      for (const row of filterData()) {
        const tr = document.createElement("tr");
        tr.innerHTML = `<td>${row.name}</td><td>${row.tokens}</td><td>$${row.cost.toFixed(2)}</td>`;
        tbody.appendChild(tr);
      }
    };

    const renderChart = () => {
      if (!ctx) return;
      const rows = filterData();
      const labels = rows.map((r) => r.name);
      const values = rows.map((r) => r.cost);
      const bg = labels.map((_, i) => `hsl(${(i * 60) % 360}, 70%, 60%)`);
      const chartData = {
        labels,
        datasets: [
          {
            data: values,
            backgroundColor: bg,
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

    groupSel.addEventListener("change", () => {
      renderTable();
      renderChart();
    });
    camSel.addEventListener("change", () => {
      renderTable();
      renderChart();
    });

    renderTable();
    renderChart();
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
        const row = document.createElement("tr");
        row.innerHTML = `<td>${name}</td><td>${data[name]}</td>`;
        tbody.appendChild(row);
        labels.push(name);
        values.push(parseFloat(data[name].replace("$", "")));
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
