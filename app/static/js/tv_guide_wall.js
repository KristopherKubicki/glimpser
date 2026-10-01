const API_URL = "/api/tv-guide-tonight";
const FETCH_TIMEOUT_MS = 28000;

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

export function programMeta(program) {
  return [program.date, program.time, program.network]
    .filter(Boolean)
    .join(" · ");
}

export function normalizePrograms(payload, limit = 8) {
  return (payload?.cards || [])
    .filter((program) => program && program.title)
    .slice(0, limit);
}

export function statusText(payload) {
  const count = Number(payload?.count || payload?.cards?.length || 0);
  return count ? `${count} programs` : "No lineup";
}

function renderProgramCard(program) {
  const card = createElement("article", "program-card");
  const body = createElement("div");
  const time = createElement("span", "program-time", programMeta(program));
  const title = createElement("h2", "", program.title);
  const episode = createElement("span", "program-meta", program.episode || "");
  const details = createElement(
    "span",
    "program-detail",
    program.details || "",
  );
  const summary = createElement("p", "program-summary", program.summary || "");

  body.append(time, title);
  if (program.episode) {
    body.append(episode);
  }
  if (program.details) {
    body.append(details);
  }
  if (program.summary) {
    body.append(summary);
  }
  card.append(body);

  if (program.image) {
    const image = createElement("img");
    image.src = program.image;
    image.alt = "";
    image.loading = "lazy";
    image.decoding = "async";
    card.append(image);
  }

  return card;
}

function renderFallback(message) {
  const grid = document.getElementById("tv-guide-grid");
  if (!grid) {
    return;
  }
  const card = createElement("article", "program-card placeholder-card");
  const body = createElement("div");
  body.append(
    createElement("span", "program-time", "TV Guide"),
    createElement("h2", "", "Lineup unavailable"),
    createElement("p", "program-summary", message),
  );
  card.append(body);
  grid.replaceChildren(card);
}

export function renderTvGuide(payload) {
  const programs = normalizePrograms(payload);
  const generatedAt = payload?.generated_at
    ? new Date(payload.generated_at)
    : null;
  const status = document.getElementById("tv-guide-status");

  setText("tv-guide-source-name", payload?.source_name || "TV Guide");
  const sourceLink = document.getElementById("tv-guide-source-name");
  if (sourceLink)
    sourceLink.href =
      payload?.source_url || "https://www.tvguide.com/new-tonight/";
  setText("tv-guide-count", String(payload?.count || programs.length || "--"));
  setText("tv-guide-next-title", programs[0]?.title || "--");
  setText("tv-guide-next-meta", programs[0] ? programMeta(programs[0]) : "--");
  setText(
    "tv-guide-updated",
    generatedAt
      ? generatedAt.toLocaleTimeString([], {
          hour: "2-digit",
          minute: "2-digit",
          timeZone: "America/Chicago",
        })
      : "--",
  );

  if (status) {
    status.dataset.state = programs.length ? "ok" : "error";
    status.textContent = programs.length
      ? statusText(payload)
      : "Lineup missing";
  }

  const grid = document.getElementById("tv-guide-grid");
  if (!grid) {
    return;
  }
  if (!programs.length) {
    renderFallback(
      payload?.message || "No upcoming evening programs returned.",
    );
    return;
  }
  grid.replaceChildren(...programs.map(renderProgramCard));
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
    const payload = await response.json();
    if (!response.ok && !Array.isArray(payload?.cards)) {
      throw new Error(`HTTP ${response.status}`);
    }
    return payload;
  } finally {
    if (timeout) {
      clearTimeout(timeout);
    }
  }
}

export async function initTvGuideWall(
  root = document.getElementById("tv-guide-wall"),
) {
  if (!root) {
    return;
  }

  try {
    renderTvGuide(await fetchJsonWithTimeout(API_URL));
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    renderFallback(message);
    const status = document.getElementById("tv-guide-status");
    if (status) {
      status.dataset.state = "error";
      status.textContent = "Fetch failed";
    }
  } finally {
    root.dataset.ready = "1";
  }
}

if (typeof document !== "undefined") {
  const autoRoot = document.querySelector("[data-tv-guide-wall-auto]");
  if (autoRoot) {
    document.addEventListener("DOMContentLoaded", () => {
      initTvGuideWall();
    });
  }
}
