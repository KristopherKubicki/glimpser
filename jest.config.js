// Jest configuration for JavaScript unit tests
// With "type": "module" in package.json, `.js` files are already
// treated as ES modules, so the config itself must use ES module syntax.
// Set TZ before Jest creates workers; changing it inside a sandboxed test
// does not update the native Date timezone. Timestamp tests exercise both
// UTC and local interpretations using America/Chicago.
process.env.TZ = "America/Chicago";

export default {
  testEnvironment: "jsdom",
  testPathIgnorePatterns: ["/node_modules/"],
  setupFiles: ["<rootDir>/tests/js/setup.js"],
};
