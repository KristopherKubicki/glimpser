// tests/js/logs.test.js
// Mock DOM elements for logs.js

document.body.innerHTML = `
  <form id="log-filter-form"></form>
  <table id="log-table"><tbody></tbody></table>
  <input id="search-input" />
  <select id="level-select"></select>
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
});
