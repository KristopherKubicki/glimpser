let cpuData = [];
const maxDataPoints = 60;

export function updatePerformanceMetrics() {
  fetch("/health")
    .then((response) => response.json())
    .then((data) => {
      const cpuVal = document.getElementById("cpu-value");
      if (cpuVal) cpuVal.textContent = `${data.cpu_usage}%`;
      const cpuBar = document.getElementById("cpu-bar");
      if (cpuBar) cpuBar.style.width = `${data.cpu_usage}%`;

      const memoryVal = document.getElementById("memory-value");
      if (memoryVal) memoryVal.textContent = `${data.memory_usage}%`;
      const memoryBar = document.getElementById("memory-bar");
      if (memoryBar) memoryBar.style.width = `${data.memory_usage}%`;

      const uptimeVal = document.getElementById("uptime-value");
      if (uptimeVal) uptimeVal.textContent = data.uptime;

      updateCPUSparkline(data.cpu_usage);
    });
}

export function updateCPUSparkline(newValue) {
  cpuData.push(newValue);
  if (cpuData.length > maxDataPoints) {
    cpuData.shift();
  }

  const canvas = document.getElementById("cpu-sparkline");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  const width = canvas.width;
  const height = canvas.height;

  ctx.clearRect(0, 0, width, height);
  ctx.strokeStyle = "#007bff";
  ctx.beginPath();

  const step = width / (maxDataPoints - 1);
  cpuData.forEach((value, index) => {
    const x = index * step;
    const y = height - (value / 100) * height;
    if (index === 0) {
      ctx.moveTo(x, y);
    } else {
      ctx.lineTo(x, y);
    }
  });

  ctx.stroke();
}

// Update metrics every 5 seconds
setInterval(updatePerformanceMetrics, 5000);

// Initial update
updatePerformanceMetrics();
