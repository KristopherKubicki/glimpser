let cpuData = [];
const maxDataPoints = 60;

function updatePerformanceMetrics() {
    fetch('/system_metrics')
        .then(response => response.json())
        .then(data => {
            document.getElementById('cpu-value').textContent = `${data.cpu_usage}%`;
            document.getElementById('cpu-bar').style.width = `${data.cpu_usage}%`;
            
            document.getElementById('memory-value').textContent = `${data.memory_usage}%`;
            document.getElementById('memory-bar').style.width = `${data.memory_usage}%`;
            
            document.getElementById('uptime-value').textContent = data.uptime;
            
            updateCPUSparkline(data.cpu_usage);
        });
}

function updateCPUSparkline(newValue) {
    cpuData.push(newValue);
    if (cpuData.length > maxDataPoints) {
        cpuData.shift();
    }
    
    const canvas = document.getElementById('cpu-sparkline');
    const ctx = canvas.getContext('2d');
    const width = canvas.width;
    const height = canvas.height;
    
    ctx.clearRect(0, 0, width, height);
    ctx.strokeStyle = '#007bff';
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

// eslint-disable-next-line no-unused-vars
function toggleScheduler() {
    fetch('/toggle_scheduler', { method: 'POST' })
        .then(response => response.json())
        .then(data => {
            const statusSpan = document.getElementById('scheduler-status');
            const toggleButton = document.getElementById('toggle-scheduler');
            statusSpan.textContent = data.status;
            toggleButton.textContent = data.status === 'running' ? 'Stop Scheduler' : 'Start Scheduler';
        })
        .catch(error => console.error('Error:', error));
}