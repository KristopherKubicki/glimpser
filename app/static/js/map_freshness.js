import { captureAge, sourceAge } from "./capture_age.js";

// A GPS fix expires independently of a successful dashboard fetch.
export function mapLocations(points = [], offline = false, now = Date.now()) {
  return points
    .filter((point) => {
      return (
        point.latitude != null &&
        point.longitude != null &&
        Number.isFinite(Number(point.latitude)) &&
        Number.isFinite(Number(point.longitude)) &&
        Math.abs(Number(point.latitude)) <= 90 &&
        Math.abs(Number(point.longitude)) <= 180
      );
    })
    .map((point) => {
      const raw = String(point.timestamp || "");
      const timestamp = Date.parse(
        /(?:Z|[+-]\d{2}:?\d{2})$/i.test(raw)
          ? raw
          : `${raw.replace(" ", "T")}Z`,
      );
      const age = (now - timestamp) / 1000;
      return {
        ...point,
        age_seconds: Number.isFinite(age) ? Math.max(0, Math.floor(age)) : null,
        stale: Boolean(
          offline ||
            point.stale ||
            !Number.isFinite(age) ||
            age < 0 ||
            age > 300,
        ),
      };
    });
}

export function mapRefreshLabel(
  updated,
  offline,
  tilesMissing,
  now = Date.now(),
) {
  const parts = [
    offline
      ? "Offline — cached positions; current location unknown"
      : "Location feed connected",
  ];
  parts.push(
    updated
      ? `Map refreshed ${captureAge(updated, now)}`
      : "Awaiting location refresh",
  );
  if (tilesMissing)
    parts.push("Basemap tiles unavailable — markers may still be available");
  return parts.join(" · ");
}

export function cameraMapStatus(camera, now = Date.now()) {
  return `${camera.issue ? camera.issue + " · " : ""}Captured ${captureAge(camera.captured, now)} · ${sourceAge(camera.freshness || {}, now)}`;
}
