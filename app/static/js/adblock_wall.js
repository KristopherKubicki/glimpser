const PROBE_TIMEOUT_MS = 3600;

export const DEFAULT_PROBES = [
  {
    id: "display",
    label: "Display ads",
    host: "pagead2.googlesyndication.com",
    description: "Google ad script endpoint used by many display ad slots.",
    url: "https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js",
  },
  {
    id: "analytics",
    label: "Analytics",
    host: "www.google-analytics.com",
    description: "Legacy analytics script that is commonly filtered.",
    url: "https://www.google-analytics.com/analytics.js",
  },
  {
    id: "social",
    label: "Social pixels",
    host: "connect.facebook.net",
    description: "Facebook event pixel delivery domain.",
    url: "https://connect.facebook.net/en_US/fbevents.js",
  },
  {
    id: "retargeting",
    label: "Retargeting",
    host: "bat.bing.com",
    description: "Microsoft advertising and retargeting beacon script.",
    url: "https://bat.bing.com/bat.js",
  },
  {
    id: "conversion",
    label: "Conversion tags",
    host: "static.ads-twitter.com",
    description: "X/Twitter universal website tag delivery endpoint.",
    url: "https://static.ads-twitter.com/uwt.js",
  },
  {
    id: "shortform",
    label: "Short-form pixels",
    host: "analytics.tiktok.com",
    description: "TikTok analytics and conversion pixel endpoint.",
    url: "https://analytics.tiktok.com/i18n/pixel/events.js",
  },
];

function setText(id, value) {
  const node = document.getElementById(id);
  if (node) {
    node.textContent = value;
  }
}

function createElement(tagName, className, text = "") {
  const node = document.createElement(tagName);
  if (className) {
    node.className = className;
  }
  if (text) {
    node.textContent = text;
  }
  return node;
}

export function normalizeProbeResult(probe, state = "pending") {
  return {
    ...probe,
    state,
    blocked: state === "blocked",
  };
}

export function scoreResults(results) {
  const total = results.length;
  const blocked = results.filter((result) => result.state === "blocked").length;
  const allowed = results.filter((result) => result.state === "allowed").length;
  const pending = total - blocked - allowed;
  const coverage = total ? Math.round((blocked / total) * 100) : 0;
  return { allowed, blocked, coverage, pending, total };
}

export function statusLabel(score) {
  if (!score.total || score.pending) {
    return "Running probes";
  }
  if (score.coverage >= 80) {
    return "Strong blocking";
  }
  if (score.coverage >= 40) {
    return "Partial blocking";
  }
  return "Mostly open";
}

export function statusState(score) {
  if (!score.total || score.pending) {
    return "";
  }
  if (score.coverage >= 80) {
    return "strong";
  }
  if (score.coverage >= 40) {
    return "partial";
  }
  return "open";
}

export function renderAdblockWall(results) {
  const score = scoreResults(results);
  const status = document.getElementById("adblock-status");
  const grid = document.getElementById("adblock-probes");

  setText("adblock-blocked", String(score.blocked));
  setText("adblock-allowed", String(score.allowed));
  setText("adblock-coverage", `${score.coverage}%`);
  setText("adblock-total", `${score.total} categories`);
  setText(
    "adblock-updated",
    new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
  );

  if (status) {
    status.dataset.state = statusState(score);
    status.textContent = statusLabel(score);
  }

  if (!grid) {
    return;
  }

  grid.replaceChildren(...results.map(renderProbeCard));
}

function renderProbeCard(result) {
  const state = result.state || "pending";
  const card = createElement("article", "probe-card");
  const statePill = createElement(
    "span",
    "probe-state",
    state === "blocked" ? "blocked" : state,
  );

  card.dataset.state = state;
  statePill.dataset.state = state;
  card.append(
    createElement("span", "probe-host", result.host || result.id),
    createElement("h2", "", result.label),
    createElement("p", "", result.description || ""),
    statePill,
  );
  return card;
}

export function runScriptProbe(probe, timeoutMs = PROBE_TIMEOUT_MS) {
  return new Promise((resolve) => {
    if (typeof document === "undefined" || !document.head) {
      resolve(normalizeProbeResult(probe, "pending"));
      return;
    }

    const script = document.createElement("script");
    const finish = (state) => {
      clearTimeout(timer);
      script.remove();
      resolve(normalizeProbeResult(probe, state));
    };
    const timer = setTimeout(() => finish("blocked"), timeoutMs);

    script.async = true;
    script.referrerPolicy = "no-referrer";
    script.src = `${probe.url}${probe.url.includes("?") ? "&" : "?"}glimpser_probe=${Date.now()}`;
    script.onload = () => finish("allowed");
    script.onerror = () => finish("blocked");
    document.head.append(script);
  });
}

export async function initAdblockWall(
  root = document.getElementById("adblock-wall"),
  probes = DEFAULT_PROBES,
) {
  if (!root) {
    return;
  }

  const pending = probes.map((probe) => normalizeProbeResult(probe));
  renderAdblockWall(pending);
  const results = await Promise.all(
    probes.map((probe) => runScriptProbe(probe)),
  );
  renderAdblockWall(results);
  root.dataset.ready = "1";
}

if (typeof document !== "undefined") {
  const autoRoot = document.querySelector("[data-adblock-wall-auto]");
  if (autoRoot) {
    document.addEventListener("DOMContentLoaded", () => {
      initAdblockWall();
    });
  }
}
