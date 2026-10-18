export const AWS_REGIONS = [
  { label: "US East / N. Virginia", code: "us-east-1", x: 316, y: 204 },
  { label: "US East / Ohio", code: "us-east-2", x: 286, y: 196 },
  { label: "US West / N. California", code: "us-west-1", x: 120, y: 220 },
  { label: "US West / Oregon", code: "us-west-2", x: 122, y: 166 },
  { label: "Canada / Central", code: "ca-central-1", x: 292, y: 132 },
  { label: "Canada / Calgary", code: "ca-west-1", x: 166, y: 126 },
  { label: "Europe / Ireland", code: "eu-west-1", x: 450, y: 168 },
  { label: "Europe / Frankfurt", code: "eu-central-1", x: 512, y: 188 },
  { label: "Europe / London", code: "eu-west-2", x: 472, y: 178 },
  { label: "Asia Pacific / Tokyo", code: "ap-northeast-1", x: 816, y: 214 },
  { label: "Asia Pacific / Singapore", code: "ap-southeast-1", x: 724, y: 344 },
  { label: "Asia Pacific / Sydney", code: "ap-southeast-2", x: 818, y: 430 },
  { label: "Asia Pacific / Mumbai", code: "ap-south-1", x: 642, y: 280 },
  { label: "South America / Sao Paulo", code: "sa-east-1", x: 386, y: 414 },
];

export const DEFAULT_SAMPLE_COUNT = 2;
export const DEFAULT_TIMEOUT_MS = 3500;

function getNow() {
  if (
    globalThis.performance &&
    typeof globalThis.performance.now === "function"
  ) {
    return globalThis.performance.now();
  }
  return Date.now();
}

function makeAbortController() {
  if (typeof AbortController !== "function") {
    return null;
  }
  return new AbortController();
}

export function endpointForRegion(code, nonce = Date.now()) {
  return `https://ec2.${code}.amazonaws.com/ping?cache_buster=${encodeURIComponent(
    String(nonce),
  )}`;
}

export function classifyLatency(ms) {
  if (!Number.isFinite(ms)) {
    return "timeout";
  }
  if (ms < 70) {
    return "fast";
  }
  if (ms < 140) {
    return "good";
  }
  if (ms < 240) {
    return "slow";
  }
  return "high";
}

export function summarizeSamples(samples) {
  const values = samples
    .map((sample) => sample.ms)
    .filter((ms) => Number.isFinite(ms))
    .sort((left, right) => left - right);

  if (!values.length) {
    return {
      mean: Number.NaN,
      min: Number.NaN,
      max: Number.NaN,
      samples: 0,
      failed: samples.length,
    };
  }

  const sum = values.reduce((total, ms) => total + ms, 0);
  return {
    mean: Math.round(sum / values.length),
    min: Math.round(values[0]),
    max: Math.round(values[values.length - 1]),
    samples: values.length,
    failed: samples.length - values.length,
  };
}

export async function measureRegion(region, options = {}) {
  const fetchImpl = options.fetchImpl || globalThis.fetch;
  const timeoutMs = options.timeoutMs || DEFAULT_TIMEOUT_MS;
  const nowFn = options.nowFn || getNow;

  if (typeof fetchImpl !== "function") {
    return { region, ms: Number.NaN, ok: false, status: "unsupported" };
  }

  const controller = makeAbortController();
  const started = nowFn();
  const timeout = controller
    ? setTimeout(() => controller.abort(), timeoutMs)
    : null;

  try {
    await fetchImpl(
      endpointForRegion(region.code, `${Date.now()}-${Math.random()}`),
      {
        cache: "no-store",
        mode: "no-cors",
        signal: controller ? controller.signal : undefined,
      },
    );
    return {
      region,
      ms: Math.round(nowFn() - started),
      ok: true,
      status: "ok",
    };
  } catch (error) {
    const elapsed = nowFn() - started;
    const aborted = error && error.name === "AbortError";
    return {
      region,
      ms: Number.NaN,
      ok: false,
      status: aborted || elapsed >= timeoutMs ? "timeout" : "error",
    };
  } finally {
    if (timeout) {
      clearTimeout(timeout);
    }
  }
}

export async function collectRegionSamples(
  regions = AWS_REGIONS,
  options = {},
) {
  const sampleCount = options.sampleCount || DEFAULT_SAMPLE_COUNT;
  const results = await Promise.all(
    regions.map(async (region) => {
      const samples = [];
      for (let index = 0; index < sampleCount; index += 1) {
        samples.push(await measureRegion(region, options));
      }
      return { region, ...summarizeSamples(samples) };
    }),
  );

  return results.sort((left, right) => {
    const leftMean = Number.isFinite(left.mean)
      ? left.mean
      : Number.POSITIVE_INFINITY;
    const rightMean = Number.isFinite(right.mean)
      ? right.mean
      : Number.POSITIVE_INFINITY;
    return leftMean - rightMean;
  });
}

function formatMs(ms) {
  return Number.isFinite(ms) ? `${Math.round(ms)} ms` : "--";
}

function signalLevel(ms) {
  if (!Number.isFinite(ms)) {
    return 5;
  }
  if (ms < 70) {
    return 1;
  }
  if (ms < 140) {
    return 2;
  }
  if (ms < 240) {
    return 3;
  }
  if (ms < 320) {
    return 4;
  }
  return 5;
}

function setText(id, text) {
  const node = document.getElementById(id);
  if (node) {
    node.textContent = text;
  }
}

function renderRows(results) {
  const rows = document.getElementById("cloudping-rows");
  if (!rows) {
    return;
  }

  rows.replaceChildren(
    ...results.map((result, index) => {
      const latencyClass = `latency-${classifyLatency(result.mean)}`;
      const row = document.createElement("tr");
      const signal = document.createElement("span");
      const signalBar = document.createElement("span");
      row.className = latencyClass;
      signal.className = "signal";
      signal.setAttribute("aria-hidden", "true");
      signalBar.className = `signal-bar signal-level-${signalLevel(result.mean)}`;
      signal.append(signalBar);
      [
        String(index + 1),
        result.region.label,
        result.region.code,
        formatMs(result.mean),
        formatMs(result.min),
        formatMs(result.max),
      ].forEach((text, cellIndex) => {
        const cell = document.createElement("td");
        cell.textContent = text;
        if (cellIndex === 1) {
          cell.className = "region-name";
        }
        row.append(cell);
      });
      const signalCell = document.createElement("td");
      signalCell.append(signal);
      row.append(signalCell);
      return row;
    }),
  );
}

function routePath(region) {
  const origin = { x: 250, y: 198 };
  const midX = (origin.x + region.x) / 2;
  const lift = Math.min(128, Math.abs(region.x - origin.x) * 0.22 + 42);
  const midY = Math.min(origin.y, region.y) - lift;
  return `M ${origin.x} ${origin.y} Q ${midX.toFixed(1)} ${midY.toFixed(
    1,
  )} ${region.x} ${region.y}`;
}

function createSvgElement(name) {
  return document.createElementNS("http://www.w3.org/2000/svg", name);
}

function renderRouteMap(results) {
  const routes = document.getElementById("route-lines");
  const points = document.getElementById("region-points");
  if (!routes || !points) {
    return;
  }

  routes.replaceChildren();
  points.replaceChildren();

  results.forEach((result, index) => {
    const latencyClass = `latency-${classifyLatency(result.mean)}`;
    const rankClass = `route-rank-${Math.min(index + 1, 6)}`;
    const path = createSvgElement("path");
    path.setAttribute("d", routePath(result.region));
    path.classList.add("route-line", latencyClass, rankClass);
    routes.append(path);

    const node = createSvgElement("g");
    const circle = createSvgElement("circle");
    const label = createSvgElement("text");
    node.classList.add("region-node", latencyClass);
    circle.setAttribute("cx", String(result.region.x));
    circle.setAttribute("cy", String(result.region.y));
    circle.setAttribute("r", index < 6 ? "6" : "4");
    label.setAttribute("x", String(result.region.x + 9));
    label.setAttribute("y", String(result.region.y - 7));
    label.textContent = result.region.code;
    node.append(circle, label);
    points.append(node);
  });
}

function updateSummary(results) {
  const measured = results.filter((result) => Number.isFinite(result.mean));
  const best = measured[0];
  const worst = measured[measured.length - 1];
  const median = measured.length
    ? measured[Math.floor((measured.length - 1) / 2)].mean
    : Number.NaN;

  setText("cloudping-best", formatMs(best ? best.mean : Number.NaN));
  setText("cloudping-best-code", best ? best.region.code : "--");
  setText("cloudping-median", formatMs(median));
  setText("cloudping-worst", formatMs(worst ? worst.mean : Number.NaN));
  setText("cloudping-worst-code", worst ? worst.region.code : "--");
  setText("cloudping-count", String(measured.length));
  setText("cloudping-updated", new Date().toLocaleTimeString());
}

export async function renderCloudpingWall(
  root = document.getElementById("latency-wall"),
) {
  if (!root) {
    return;
  }

  root.dataset.ready = "0";
  setText("cloudping-status", "Measuring regions");

  try {
    const results = await collectRegionSamples();
    renderRows(results);
    renderRouteMap(results);
    updateSummary(results);
    setText("cloudping-status", "Ready");
    root.dataset.ready = "1";
  } catch (error) {
    console.error("Cloudping wall failed", error);
    setText("cloudping-status", "Probe error");
    root.dataset.ready = "1";
  }
}

function shouldAutoStart() {
  return Boolean(
    typeof document !== "undefined" &&
      document.body &&
      document.body.hasAttribute("data-cloudping-auto"),
  );
}

if (shouldAutoStart()) {
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => renderCloudpingWall(), {
      once: true,
    });
  } else {
    renderCloudpingWall();
  }
}
