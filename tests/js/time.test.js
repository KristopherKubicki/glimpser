// tests/js/time.test.js

document.body.innerHTML = `<div id="index-time"></div>`;

jest.useFakeTimers();

const { initIndexTime } = require('../../app/static/js/time.js');

describe('time.js', () => {
  test('initIndexTime updates element with time and ISO title', () => {
    initIndexTime();
    jest.advanceTimersByTime(0);
    const elem = document.getElementById('index-time');
    expect(elem.textContent).not.toBe('');
    expect(elem.title).toMatch(/T\d{2}:\d{2}:\d{2}\.\d{3}Z/);
  });
});

