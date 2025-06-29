// Extract camera names from server-provided details

/**
 * Return camera names excluding group keys.
 * @param {Record<string, unknown>} details - Data keyed by camera.
 * @returns {string[]} Array of camera names.
 */
export function getCameraNames(details) {
  return Object.keys(details).filter(
    (key) => key !== "All" && !key.startsWith("group-"),
  );
}
