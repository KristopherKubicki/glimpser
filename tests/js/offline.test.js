import { jest } from '@jest/globals';

Object.defineProperty(global.navigator, 'serviceWorker', {
  value: {
    register: jest.fn(() => Promise.resolve()),
  },
  configurable: true,
});

let initOffline;

beforeAll(async () => {
  const mod = await import('../../app/static/js/offline.js');
  initOffline = mod.initOffline;
});

describe('offline.js', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  test('registers the service worker automatically', () => {
    initOffline();
    expect(navigator.serviceWorker.register).toHaveBeenCalledWith('/sw.js');
  });
});
