module.exports = {
  testEnvironment: 'jsdom',
  // Treat .js files as ES modules so dynamic imports work in tests
  extensionsToTreatAsEsm: ['.js'],
  testPathIgnorePatterns: ['/node_modules/', 'tests/playwright/'],
};
