import { jest } from '@jest/globals';
// tests/js/logs.test.js
// Mock DOM elements for logs.js

document.body.innerHTML = `
  <form id="log-filter-form"></form>
  <table id="log-table"><tbody></tbody></table>
  <input id="search-input" />
  <select id="level-select"></select>
  <div id="log-connection-status" class="hidden"></div>
`;

let updateTable;

beforeAll(async () => {
  const mod = await import('../../app/static/js/logs.js');
  updateTable = mod.updateTable;
});

describe('logs.js', () => {
  beforeEach(() => {
    document.querySelector('#log-table tbody').innerHTML = '';
  });

  test('updateTable populates rows based on log data', () => {
    const logs = [
      { timestamp: 'now', level: 'INFO', source: 'system', message: 'a' },
      { timestamp: 'later', level: 'WARN', source: 'system', message: 'b' },
    ];

    updateTable(logs);

    const rows = document.querySelectorAll('#log-table tbody tr');
    expect(rows).toHaveLength(2);
    expect(rows[0].textContent).toContain('INFO');
    expect(rows[1].textContent).toContain('WARN');
  });

  test('reconnects when the event stream errors', () => {
    jest.useFakeTimers();
    const esInstances = [];
    global.EventSource = jest.fn(() => {
      const es = { onmessage: null, onerror: null, onopen: null, close: jest.fn() };
      esInstances.push(es);
      return es;
    });

    document.dispatchEvent(new Event('DOMContentLoaded'));
    expect(EventSource).toHaveBeenCalledTimes(1);

    esInstances[0].onerror(new Event('error'));
    const status = document.getElementById('log-connection-status');
    expect(status.classList.contains('hidden')).toBe(false);

    jest.advanceTimersByTime(3000);
    expect(EventSource).toHaveBeenCalledTimes(2);

    esInstances[1].onopen();
    expect(status.classList.contains('hidden')).toBe(true);
  });
});
