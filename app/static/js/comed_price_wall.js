const API_URL = "/api/comed-price";
const FETCH_TIMEOUT_MS = 8000;
const SVG_NS = "http://www.w3.org/2000/svg";

const CHART = {
  left: 74,
  right: 1146,
  top: 44,
  bottom: 448,
};

function asNumber(value) {
  if (value === null || value === undefined || value === "") {
    return Number.NaN;
  }
  const number = Number(value);
  return Number.isFinite(number) ? number : Number.NaN;
}

function createSvgElement(tagName, attributes = {}) {
  const node = document.createElementNS(SVG_NS, tagName);
  Object.entries(attributes).forEach(([name, value]) => {
    if (value !== undefined && value !== null) {
      node.setAttribute(name, String(value));
    }
  });
  return node;
}

function replaceChildren(node, children) {
  if (!node) {
    return;
  }
  node.replaceChildren(...children);
}

function setText(id, value) {
  const node = document.getElementById(id);
  if (node) {
    node.textContent = value;
  }
}

export function formatPrice(value) {
  const number = asNumber(value);
  if (!Number.isFinite(number)) {
    return "--";
  }
  return `${number.toFixed(1)} cents`;
}

export function averagePrice(points) {
  const values = points
    .map((point) => asNumber(point.value))
    .filter((value) => Number.isFinite(value));
  if (!values.length) {
    return Number.NaN;
  }
  return values.reduce((total, value) => total + value, 0) / values.length;
}

export function peakPoint(points) {
  let peak = { value: Number.NaN, hour: null };
  points.forEach((point) => {
    const value = asNumber(point.value);
    if (!Number.isFinite(value)) {
      return;
    }
    if (
      !Number.isFinite(asNumber(peak.value)) ||
      value > asNumber(peak.value)
    ) {
      peak = point;
    }
  });
  return peak;
}

export function priceBand(value) {
  const number = asNumber(value);
  if (!Number.isFinite(number)) {
    return "unknown";
  }
  if (number >= 14) {
    return "critical";
  }
  if (number >= 8) {
    return "high";
  }
  if (number <= 2) {
    return "cheap";
  }
  return "normal";
}

function usablePoints(points) {
  return (points || []).filter((point) =>
    Number.isFinite(asNumber(point.value)),
  );
}

export function selectChartSeries(payload) {
  const series = payload && payload.series ? payload.series : {};
  return {
    actual: usablePoints(series.actual),
    dayAhead: usablePoints(series.day_ahead),
    actualLabel: payload?.actual_label || "settled hourly price",
  };
}

function pointHour(point, fallbackIndex = 0) {
  const hour = asNumber(point.hour);
  const minute = asNumber(point.minute);
  if (!Number.isFinite(hour)) {
    return fallbackIndex;
  }
  return hour + (Number.isFinite(minute) ? minute / 60 : 0);
}

export function chartDomain(...seriesList) {
  const values = seriesList
    .flat()
    .map((point) => asNumber(point.value))
    .filter((value) => Number.isFinite(value));
  const maxValue = values.length ? Math.max(...values, 8) : 8;
  const minValue = values.length ? Math.min(...values, 0) : 0;
  return {
    min: Math.floor(Math.min(0, minValue)),
    max: Math.ceil(maxValue + 1),
  };
}

function xForHour(hour) {
  const width = CHART.right - CHART.left;
  return CHART.left + (Math.max(0, Math.min(23, hour)) / 23) * width;
}

function yForValue(value, domain) {
  const height = CHART.bottom - CHART.top;
  const span = Math.max(1, domain.max - domain.min);
  return CHART.bottom - ((value - domain.min) / span) * height;
}

export function linePath(points, domain) {
  return points
    .map((point, index) => {
      const x = xForHour(pointHour(point, index));
      const y = yForValue(asNumber(point.value), domain);
      return `${index === 0 ? "M" : "L"}${x.toFixed(1)} ${y.toFixed(1)}`;
    })
    .join(" ");
}

function renderAxis(domain) {
  const children = [];
  const yTicks = 5;
  for (let index = 0; index <= yTicks; index += 1) {
    const value = domain.min + ((domain.max - domain.min) / yTicks) * index;
    const y = yForValue(value, domain);
    children.push(
      createSvgElement("line", {
        x1: CHART.left,
        x2: CHART.right,
        y1: y,
        y2: y,
      }),
    );
    const label = createSvgElement("text", {
      x: 22,
      y: y + 6,
    });
    label.textContent = `${Math.round(value)}c`;
    children.push(label);
  }

  [0, 6, 12, 18, 23].forEach((hour) => {
    const x = xForHour(hour);
    children.push(
      createSvgElement("line", {
        x1: x,
        x2: x,
        y1: CHART.top,
        y2: CHART.bottom,
      }),
    );
    const label = createSvgElement("text", {
      x: x - 17,
      y: 486,
    });
    label.textContent = `${String(hour).padStart(2, "0")}:00`;
    children.push(label);
  });

  replaceChildren(document.getElementById("comed-axis"), children);
}

function renderThresholds(domain) {
  const children = [];
  const highY = yForValue(8, domain);
  const criticalY = yForValue(14, domain);
  if (domain.max >= 14) {
    children.push(
      createSvgElement("rect", {
        class: "threshold-zone",
        x: CHART.left,
        y: CHART.top,
        width: CHART.right - CHART.left,
        height: Math.max(0, criticalY - CHART.top),
      }),
    );
  }
  if (domain.max >= 8) {
    children.push(
      createSvgElement("line", {
        class: "threshold-line",
        x1: CHART.left,
        x2: CHART.right,
        y1: highY,
        y2: highY,
      }),
    );
    const label = createSvgElement("text", {
      class: "threshold-label",
      x: CHART.right - 118,
      y: highY - 9,
    });
    label.textContent = "8c watch";
    children.push(label);
  }
  replaceChildren(document.getElementById("comed-thresholds"), children);
}

function renderDayAheadBars(points, domain) {
  const baselineY = yForValue(Math.max(0, domain.min), domain);
  const barWidth = 28;
  const children = points.map((point, index) => {
    const value = asNumber(point.value);
    const x = xForHour(pointHour(point, index)) - barWidth / 2;
    const y = yForValue(value, domain);
    return createSvgElement("rect", {
      class: `day-ahead-bar is-${priceBand(value)}`,
      x,
      y: Math.min(y, baselineY),
      width: barWidth,
      height: Math.max(2, Math.abs(baselineY - y)),
      rx: 2,
    });
  });
  replaceChildren(document.getElementById("comed-day-ahead-bars"), children);
}

function renderActualLine(points, domain, currentPrice) {
  const children = [];
  if (points.length) {
    children.push(
      createSvgElement("path", {
        class: "actual-path",
        d: linePath(points, domain),
      }),
    );
    points.forEach((point, index) => {
      children.push(
        createSvgElement("circle", {
          class: "actual-point",
          cx: xForHour(pointHour(point, index)),
          cy: yForValue(asNumber(point.value), domain),
          r: 4,
        }),
      );
    });
  }

  if (Number.isFinite(asNumber(currentPrice))) {
    const now = new Date();
    children.push(
      createSvgElement("circle", {
        class: "current-point",
        cx: xForHour(now.getHours() + now.getMinutes() / 60),
        cy: yForValue(asNumber(currentPrice), domain),
        r: 7,
      }),
    );
  }

  replaceChildren(document.getElementById("comed-actual-line"), children);
}

function renderPointLabels(points, domain) {
  const peak = peakPoint(points);
  const children = [];
  if (Number.isFinite(asNumber(peak.value))) {
    const x = xForHour(pointHour(peak));
    const y = yForValue(asNumber(peak.value), domain);
    const label = createSvgElement("text", {
      x: Math.min(x + 10, CHART.right - 115),
      y: Math.max(y - 12, CHART.top + 20),
    });
    label.textContent = `peak ${formatPrice(peak.value)}`;
    children.push(label);
  }
  replaceChildren(document.getElementById("comed-point-labels"), children);
}

function updateMetrics(payload, actual, dayAhead) {
  const currentPrice = asNumber(payload.current_price);
  const peak = peakPoint([...dayAhead, ...actual]);
  const generatedAt = payload.generated_at
    ? new Date(payload.generated_at)
    : null;
  const warningCount = Array.isArray(payload.warnings)
    ? payload.warnings.length
    : 0;

  setText("comed-current-price", formatPrice(currentPrice));
  setText("comed-current-window", payload.current_interval || "live feed");
  setText("comed-day-ahead-average", formatPrice(averagePrice(dayAhead)));
  setText("comed-actual-average", formatPrice(averagePrice(actual)));
  setText("comed-actual-label", payload.actual_label || "settled hourly price");
  setText(
    "comed-actual-legend",
    payload.actual_label || "settled hourly price",
  );
  setText("comed-peak-price", formatPrice(peak.value));
  setText(
    "comed-peak-hour",
    Number.isFinite(asNumber(peak.hour))
      ? `${String(peak.hour).padStart(2, "0")}:00`
      : "--",
  );
  setText(
    "comed-updated",
    generatedAt
      ? generatedAt.toLocaleTimeString([], {
          timeZone: "America/Chicago",
          timeZoneName: "short",
          hour: "2-digit",
          minute: "2-digit",
        })
      : "--",
  );

  const status = document.getElementById("comed-feed-status");
  if (status) {
    status.dataset.state = payload.ok
      ? warningCount
        ? "warn"
        : "ok"
      : "error";
    status.textContent = payload.ok
      ? warningCount
        ? "Fallback active"
        : "Feed live"
      : "Feed unavailable";
  }

  const warning = document.getElementById("comed-warning");
  if (warning) {
    warning.textContent = warningCount
      ? `Note: ${payload.warnings.join(", ")}`
      : `Market date ${payload.market_date || "--"} (${payload.market_timezone || "ComEd"})`;
  }
}

export function renderComedPrice(payload) {
  const { actual, dayAhead } = selectChartSeries(payload);
  const domain = chartDomain(actual, dayAhead, [
    { value: payload.current_price || Number.NaN },
  ]);

  renderThresholds(domain);
  renderAxis(domain);
  renderDayAheadBars(dayAhead, domain);
  renderActualLine(actual, domain, payload.current_price);
  renderPointLabels([...actual, ...dayAhead], domain);
  updateMetrics(payload, actual, dayAhead);
}

async function fetchJsonWithTimeout(url, timeoutMs = FETCH_TIMEOUT_MS) {
  const controller =
    typeof AbortController === "function" ? new AbortController() : null;
  const timeout = controller
    ? setTimeout(() => controller.abort(), timeoutMs)
    : null;
  try {
    const response = await fetch(url, {
      cache: "no-store",
      signal: controller ? controller.signal : undefined,
    });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    return await response.json();
  } finally {
    if (timeout) {
      clearTimeout(timeout);
    }
  }
}

export async function initComedPriceWall(
  root = document.getElementById("comed-price-wall"),
) {
  if (!root) {
    return;
  }

  try {
    const payload = await fetchJsonWithTimeout(API_URL);
    renderComedPrice(payload);
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    renderComedPrice({
      ok: false,
      current_price: null,
      current_interval: "ComEd API unavailable",
      actual_label: "settled hourly price",
      series: { actual: [], day_ahead: [] },
      warnings: [message],
    });
  } finally {
    root.dataset.ready = "1";
  }
}

if (typeof document !== "undefined") {
  const autoRoot = document.querySelector("[data-comed-price-wall-auto]");
  if (autoRoot) {
    document.addEventListener("DOMContentLoaded", () => {
      initComedPriceWall();
    });
  }
}
