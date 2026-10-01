// Only a newer event on the same property's door may supersede its approach.
export function canHandoffToDoor(next, previous, now = Date.now()) {
  let approaches;
  try {
    const rules = JSON.parse(
      document.getElementById("priority-handoff-settings")?.textContent || "{}",
    );
    if (!Object.hasOwn(rules, next?.camera_name)) return false;
    approaches = rules[next.camera_name];
  } catch {
    return false;
  }
  if (
    !next?.priority ||
    !previous?.priority ||
    next.key === previous.key ||
    !Array.isArray(approaches) ||
    !approaches.includes(previous.camera_name)
  )
    return false;
  const timestamp = (value) => {
    if (typeof value !== "string") return NaN;
    return Date.parse(
      /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/.test(value)
        ? value.replace(" ", "T") + "Z"
        : value,
    );
  };
  const nextAt = timestamp(next.occurred_at);
  const previousAt = timestamp(previous.occurred_at);
  return (
    Number.isFinite(nextAt) &&
    Number.isFinite(previousAt) &&
    nextAt > previousAt &&
    nextAt <= now &&
    now - nextAt <= 120000
  );
}
