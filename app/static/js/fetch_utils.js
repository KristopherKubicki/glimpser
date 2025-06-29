// Lightweight fetch wrapper returning parsed JSON

/**
 * Fetch JSON from a URL with error handling.
 * @param {string} url - Target endpoint.
 * @param {RequestInit} [options] - Fetch options.
 * @returns {Promise<unknown>} Parsed response body.
 */
export async function fetchJson(url, options = {}) {
  try {
    const res = await fetch(url, options);
    if (!res.ok) {
      // Read text for more informative error messages
      const text = await res.text();
      throw new Error(text || res.statusText);
    }
    return await res.json();
  } catch (err) {
    console.error(`Fetch failed for ${url}:`, err);
    throw err;
  }
}
