// Jest configuration for JavaScript unit tests
// `type: module` in package.json means `.js` files are ESM, so the config
// itself must also use ES module syntax.
export default {
  testEnvironment: 'jsdom',
  // Treat .js files as ES modules so dynamic imports work in tests
  extensionsToTreatAsEsm: ['.js'],
  testPathIgnorePatterns: ['/node_modules/', 'tests/playwright/'],
};
