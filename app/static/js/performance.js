let cpuData = [];
let memoryData = [];
let diskData = [];
const maxDataPoints = 60;

function setProgress(el, value) {
  if (!el) return;
  if (el.tagName === "PROGRESS") {
    el.value = value;
  } else {
    el.style.width = `${value}%`;
  }
}

function setStatus(el, status) {
  if (!el) return;
  el.classList.remove("ok", "slow", "error");
  el.classList.add(status);
}

export function updatePerformanceMetrics() {
  return fetch("/health")
    .then((response) => response.json())
    .then((data) => {
      const metrics = data.metrics || data;

      const cpuVal = document.getElementById("cpu-value");
      if (cpuVal) cpuVal.textContent = `${metrics.cpu_usage}%`;
      setProgress(document.getElementById("cpu-bar"), metrics.cpu_usage);

      const memoryVal = document.getElementById("memory-value");
      if (memoryVal) memoryVal.textContent = `${metrics.memory_usage}%`;
      setProgress(document.getElementById("memory-bar"), metrics.memory_usage);

      const diskVal = document.getElementById("disk-value");
      if (diskVal) diskVal.textContent = `${metrics.disk_usage}%`;
      setProgress(document.getElementById("disk-bar"), metrics.disk_usage);

      const openFiles = document.getElementById("open-files");
      if (openFiles) openFiles.textContent = metrics.open_files;

      const threadCount = document.getElementById("thread-count");
      if (threadCount) threadCount.textContent = metrics.thread_count;

      const uptimeVal = document.getElementById("uptime-value");
      if (uptimeVal) uptimeVal.textContent = metrics.uptime;

      const gpuStatus = document.getElementById("gpu-status");
      if (metrics.ffmpeg_gpu_enabled) {
        setStatus(gpuStatus, "ok");
      } else if (metrics.gpu_support) {
        setStatus(gpuStatus, "slow");
      } else {
        setStatus(gpuStatus, "error");
      }

      updateCPUSparkline(metrics.cpu_usage);
      updateMemorySparkline(metrics.memory_usage);
      updateDiskSparkline(metrics.disk_usage);
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

export function updateMemorySparkline(newValue) {
  memoryData.push(newValue);
  if (memoryData.length > maxDataPoints) {
    memoryData.shift();
  }

  const canvas = document.getElementById("memory-sparkline");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  const width = canvas.width;
  const height = canvas.height;

  ctx.clearRect(0, 0, width, height);
  ctx.strokeStyle = "#28a745";
  ctx.beginPath();

  const step = width / (maxDataPoints - 1);
  memoryData.forEach((value, index) => {
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

export function updateDiskSparkline(newValue) {
  diskData.push(newValue);
  if (diskData.length > maxDataPoints) {
    diskData.shift();
  }

  const canvas = document.getElementById("disk-sparkline");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  const width = canvas.width;
  const height = canvas.height;

  ctx.clearRect(0, 0, width, height);
  ctx.strokeStyle = "#ffc107";
  ctx.beginPath();

  const step = width / (maxDataPoints - 1);
  diskData.forEach((value, index) => {
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
