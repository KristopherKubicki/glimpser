// Mock the fetch function
global.fetch = jest.fn(() =>
  Promise.resolve({
    json: () => Promise.resolve({ /* mock data */ }),
  })
);

// Mock the DOM elements
document.body.innerHTML = `
  <div id="template-list"></div>
  <select id="group-dropdown"></select>
  <input id="grid-width-slider" type="range">
`;

// Import the functions to test
const {
  loadTemplates,
  updateGridLayout,
  timeAgo,
} = require('../../app/static/js/script.js');

describe('script.js', () => {
  beforeEach(() => {
    // Clear all mocks before each test
    jest.clearAllMocks();
  });

  test('loadTemplates fetches data and updates the DOM', async () => {
    // Mock the fetch response
    global.fetch.mockResolvedValueOnce({
      json: () => Promise.resolve({
        template1: { last_screenshot_time: new Date().toISOString() },
        template2: { last_screenshot_time: new Date().toISOString() },
      }),
    });

    await loadTemplates();

    expect(fetch).toHaveBeenCalledWith('/templates');
    expect(document.getElementById('template-list').children.length).toBe(2);
  });

  test('updateGridLayout changes layout based on screen size', () => {
    const templateList = document.getElementById('template-list');

    // Mock mobile device
    window.matchMedia = jest.fn().mockImplementation(query => ({
      matches: query === "(hover: none)",
      addListener: jest.fn(),
      removeListener: jest.fn(),
    }));

    updateGridLayout();
    expect(templateList.style.gridTemplateColumns).toBe('1fr');

    // Mock desktop device
    window.matchMedia = jest.fn().mockImplementation(query => ({
      matches: query !== "(hover: none)",
      addListener: jest.fn(),
      removeListener: jest.fn(),
    }));

    updateGridLayout();
    expect(templateList.style.gridTemplateColumns).toBe('repeat(auto-fit, minmax(50px, var(--grid-item-width, 360px)))');
  });

  test('timeAgo returns correct human-readable time', () => {
    const now = new Date();
    const oneMinuteAgo = new Date(now.getTime() - 60000);
    const oneHourAgo = new Date(now.getTime() - 3600000);
    const oneDayAgo = new Date(now.getTime() - 86400000);

    expect(timeAgo(now)).toBe('just now');
    expect(timeAgo(oneMinuteAgo)).toBe('1 minute ago');
    expect(timeAgo(oneHourAgo)).toBe('1 hour ago');
    expect(timeAgo(oneDayAgo)).toBe('1 day ago');
  });
});