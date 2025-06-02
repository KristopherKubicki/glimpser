export async function fetchJson(url, options = {}) {
  // Wrapper to fetch JSON with basic error handling
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
