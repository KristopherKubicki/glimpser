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
