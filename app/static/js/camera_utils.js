/**
 * Utility functions for camera-related lookups.
 */

/**
 * Extract camera names from the details object.
 *
 * @param {Object} details Mapping of camera info keyed by name.
 * @returns {string[]} Array of camera names.
 */
export function getCameraNames(details) {
  return Object.keys(details).filter(
    (key) => key !== "All" && !key.startsWith("group-"),
  );
}
