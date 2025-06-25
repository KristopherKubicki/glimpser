export function getCameraNames(details) {
  return Object.keys(details).filter(
    (key) => key !== "All" && !key.startsWith("group-"),
  );
}
