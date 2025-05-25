// tests/js/performance.test.js
// Mock DOM structure required by performance.js

document.body.innerHTML = `
  <div id="cpu-value"></div>
  <div id="cpu-bar"></div>
  <div id="memory-value"></div>
  <div id="memory-bar"></div>
  <div id="uptime-value"></div>
  <canvas id="cpu-sparkline" width="100" height="20"></canvas>
`;

// Provide a mock canvas context
const canvas = document.getElementById('cpu-sparkline');
canvas.getContext = jest.fn(() => ({
  clearRect: jest.fn(),
  beginPath: jest.fn(),
  moveTo: jest.fn(),
  lineTo: jest.fn(),
  stroke: jest.fn(),
}));

// Import functions to test
const {
  updatePerformanceMetrics,
  updateCPUSparkline,
} = require('../../app/static/js/performance.js');

describe('performance.js', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  test('updatePerformanceMetrics fetches metrics and updates DOM', async () => {
    const mockData = { cpu_usage: 50, memory_usage: 40, uptime: '1h' };
    global.fetch = jest.fn(() => Promise.resolve({ json: () => Promise.resolve(mockData) }));
    const sparkSpy = jest.spyOn(module, 'updateCPUSparkline');

    await updatePerformanceMetrics();

    expect(fetch).toHaveBeenCalledWith('/system_metrics');
    expect(document.getElementById('cpu-value').textContent).toBe('50%');
    expect(document.getElementById('memory-value').textContent).toBe('40%');
    expect(document.getElementById('uptime-value').textContent).toBe('1h');
    expect(sparkSpy).toHaveBeenCalledWith(50);
  });

  test('updateCPUSparkline draws on the canvas', () => {
    updateCPUSparkline(10);
    const ctx = canvas.getContext();
    expect(ctx.clearRect).toHaveBeenCalled();
    expect(ctx.beginPath).toHaveBeenCalled();
    expect(ctx.moveTo).toHaveBeenCalled();
    expect(ctx.lineTo).toHaveBeenCalled();
    expect(ctx.stroke).toHaveBeenCalled();
  });
});
