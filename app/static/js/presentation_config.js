/** Resolve installation labels supplied only by authorized dashboard pages. */
export function presentationValue(fallback) {
  try {
    const element = globalThis.document?.getElementById(
      "presentation-settings",
    );
    const settings = JSON.parse(element?.textContent || "{}");
    const value = Object.hasOwn(settings, fallback) ? settings[fallback] : null;
    return typeof value === "string" && value.trim() && value.length <= 240
      ? value.trim()
      : fallback;
  } catch {
    return fallback;
  }
}
