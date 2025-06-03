// Jest configuration for JavaScript unit tests
// With "type": "module" in package.json, `.js` files are already
// treated as ES modules, so the config itself must use ES module syntax.
export default {
  testEnvironment: 'jsdom',
  testPathIgnorePatterns: ['/node_modules/', 'tests/playwright/'],
  setupFiles: ['<rootDir>/tests/js/setup.js'],
};
