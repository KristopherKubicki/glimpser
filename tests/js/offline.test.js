// tests/js/offline.test.js

// Mock DOM element
document.body.innerHTML = `
  <input type="checkbox" id="offline-preview" />
`;

// Provide mock serviceWorker APIs
Object.defineProperty(global.navigator, 'serviceWorker', {
  value: {
    register: jest.fn(() => Promise.resolve()),
    getRegistrations: jest.fn(() =>
      Promise.resolve([
        { active: { scriptURL: '/sw.js' }, unregister: jest.fn() },
      ]),
    ),
  },
  configurable: true,
});

// Import the function to test
const { initOffline } = require('../../app/static/js/offline.js');

describe('offline.js', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    localStorage.clear();
  });

  test('checking the box registers the service worker', () => {
    initOffline();
    const checkbox = document.getElementById('offline-preview');
    checkbox.checked = true;
    checkbox.dispatchEvent(new Event('change'));

    expect(localStorage.getItem('offlinePreviewEnabled')).toBe('true');
    expect(navigator.serviceWorker.register).toHaveBeenCalledWith('/sw.js');
  });

  test('unchecking the box unregisters the service worker', async () => {
    initOffline();
    const checkbox = document.getElementById('offline-preview');

    // enable then disable
    checkbox.checked = true;
    checkbox.dispatchEvent(new Event('change'));

    checkbox.checked = false;
    checkbox.dispatchEvent(new Event('change'));

    expect(localStorage.getItem('offlinePreviewEnabled')).toBeNull();
    expect(navigator.serviceWorker.getRegistrations).toHaveBeenCalled();
  });
});
