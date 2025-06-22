import { jest } from '@jest/globals';
// tests/js/performance.test.js
// Mock DOM structure required by performance.js

document.body.innerHTML = `
  <div id="cpu-value"></div>
  <div id="cpu-bar"></div>
  <div id="memory-value"></div>
  <div id="memory-bar"></div>
  <div id="disk-value"></div>
  <div id="disk-bar"></div>
  <div id="open-files"></div>
  <div id="thread-count"></div>
  <div id="uptime-value"></div>
  <canvas id="cpu-sparkline" width="100" height="20"></canvas>
  <canvas id="memory-sparkline" width="100" height="20"></canvas>
  <canvas id="disk-sparkline" width="100" height="20"></canvas>
`;

// Provide a mock canvas context
const canvas = document.getElementById('cpu-sparkline');
const memoryCanvas = document.getElementById('memory-sparkline');
const diskCanvas = document.getElementById('disk-sparkline');
const ctx = {
  clearRect: jest.fn(),
  beginPath: jest.fn(),
  moveTo: jest.fn(),
  lineTo: jest.fn(),
  stroke: jest.fn(),
};
canvas.getContext = jest.fn(() => ctx);
memoryCanvas.getContext = jest.fn(() => ctx);
diskCanvas.getContext = jest.fn(() => ctx);

let performanceModule;
let updatePerformanceMetrics;
let updateCPUSparkline;
let updateMemorySparkline;
let updateDiskSparkline;

beforeAll(async () => {
  global.fetch = jest.fn(() => Promise.resolve({ json: () => Promise.resolve({}) }));
  global.setInterval = jest.fn();
  performanceModule = await import('../../app/static/js/performance.js');
  updatePerformanceMetrics = performanceModule.updatePerformanceMetrics;
  updateCPUSparkline = performanceModule.updateCPUSparkline;
  updateMemorySparkline = performanceModule.updateMemorySparkline;
  updateDiskSparkline = performanceModule.updateDiskSparkline;
});

describe('performance.js', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  test('updatePerformanceMetrics fetches metrics and updates DOM', async () => {
    const mockData = {
      cpu_usage: 50,
      memory_usage: 40,
      disk_usage: 70,
      open_files: 5,
      thread_count: 8,
      uptime: '1h',
    };
    global.fetch = jest.fn(() => Promise.resolve({ json: () => Promise.resolve(mockData) }));

    await updatePerformanceMetrics();

    expect(fetch).toHaveBeenCalledWith('/health');
    expect(document.getElementById('cpu-value').textContent).toBe('50%');
    expect(document.getElementById('memory-value').textContent).toBe('40%');
    expect(document.getElementById('disk-value').textContent).toBe('70%');
    expect(document.getElementById('open-files').textContent).toBe('5');
    expect(document.getElementById('thread-count').textContent).toBe('8');
    expect(document.getElementById('uptime-value').textContent).toBe('1h');

    expect(canvas.getContext).toHaveBeenCalled();
    expect(memoryCanvas.getContext).toHaveBeenCalled();
    expect(diskCanvas.getContext).toHaveBeenCalled();
  });

  test('sparkline functions draw on their canvases', () => {
    updateCPUSparkline(10);
    updateMemorySparkline(20);
    updateDiskSparkline(30);
    const ctxRef = canvas.getContext();
    expect(ctxRef.clearRect).toHaveBeenCalled();
    expect(ctxRef.beginPath).toHaveBeenCalled();
    expect(ctxRef.moveTo).toHaveBeenCalled();
    expect(ctxRef.lineTo).toHaveBeenCalled();
    expect(ctxRef.stroke).toHaveBeenCalled();
  });
});
