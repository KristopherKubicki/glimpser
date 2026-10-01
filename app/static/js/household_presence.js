import { captureAge } from "./capture_age.js";

const element = (tag, text, className = "") => {
  const node = document.createElement(tag);
  node.textContent = text;
  node.className = className;
  return node;
};
const stateLabel = (value) =>
  value === "present" ? "Home" : value === "not present" ? "Away" : "Unknown";

export function renderPresence(
  host,
  payload,
  offline = false,
  now = Date.now(),
) {
  const historyOpen = host.querySelector(".household-history")?.open;
  const expanded = new Set(
    Array.from(host.querySelectorAll(".household-sources[open]")).map(
      (node) => node.dataset.subject,
    ),
  );
  const compact = Boolean(host.closest("[data-visual-dashboard]"));
  host.replaceChildren(element("h2", "Household presence"));
  host.append(
    element(
      "p",
      offline
        ? "Connection unavailable · last received information"
        : "Confirmed presence · phone, hub and vehicle signals",
      "household-note",
    ),
  );
  const grid = element("div", "", "household-grid vd-gallery");
  for (const subject of payload.subjects || []) {
    const card = element("article", "", "household-person vd-card");
    const verified = Date.parse(subject.verified_at || "");
    const stale =
      offline ||
      subject.stale ||
      !Number.isFinite(verified) ||
      now - verified > 120000 ||
      verified > now;
    const state = stale ? "Unknown" : stateLabel(subject.presence);
    const heading = element("header");
    heading.append(
      element("h3", subject.label),
      element("span", state, "household-status vd-age"),
    );
    card.append(heading);
    if (stale && subject.last_presence && subject.last_presence !== "unknown")
      card.append(
        element(
          "p",
          `Last confirmed ${stateLabel(subject.last_presence).toLowerCase()} · ${captureAge(subject.verified_at, now)}`,
        ),
      );
    else
      card.append(
        element(
          "p",
          subject.verified_at
            ? `Verified ${captureAge(subject.verified_at, now)}`
            : "Awaiting a connected presence source",
        ),
      );
    let info = card;
    if (compact) {
      info = element("details", "", "household-sources");
      info.dataset.subject = subject.label;
      info.open = expanded.has(subject.label);
      info.append(element("summary", "Presence details"));
      card.append(info);
    }
    heading.dataset.presenceState = state.toLowerCase();
    info.append(element("p", subject.status_note || ""));
    if (subject.location_identity)
      info.append(element("p", subject.location_identity, "vd-source"));
    if (subject.position)
      info.append(
        element(
          "p",
          `GPS updated ${captureAge(subject.position.timestamp, now)} · ${subject.position_status}`,
          "vd-source",
        ),
      );
    for (const source of subject.sources || [])
      info.append(
        element(
          "p",
          `${source.label}: ${source.available ? stateLabel(source.presence) : "Unavailable"}`,
          "vd-source",
        ),
      );
    grid.append(card);
  }
  host.append(grid);
  const history = element("details", "", "household-history");
  history.append(element("summary", "Recent arrivals and departures"));
  const list = element("ol");
  for (const event of (payload.presence_events || []).slice(0, 12)) {
    const item = element(
      "li",
      `${event.label} ${event.kind === "arrival" ? "arrived" : "left"} · ${captureAge(event.occurred_at, now)}`,
    );
    item.append(element("p", event.reason));
    list.append(item);
  }
  if (!list.childElementCount)
    list.append(element("li", "No confirmed transitions recorded yet."));
  history.open = Boolean(historyOpen);
  history.append(list);
  host.append(history);
}

export function mountPresence(host) {
  let payload = { subjects: [] },
    offline = false,
    pending = false;
  const refresh = async () => {
    if (pending || document.hidden) return;
    pending = true;
    const controller =
      typeof AbortController === "function" ? new AbortController() : null;
    const timeout = window.setTimeout(() => controller?.abort(), 7000);
    try {
      const response = await fetch("/api/household-presence", {
        cache: "no-store",
        signal: controller?.signal,
      });
      if (!response.ok) throw Error("Presence unavailable");
      payload = await response.json();
      offline = false;
    } catch {
      offline = true;
    } finally {
      window.clearTimeout(timeout);
      pending = false;
      renderPresence(host, payload, offline);
    }
  };
  refresh();
  const timer = window.setInterval(refresh, 30000);
  const ages = window.setInterval(
    () => renderPresence(host, payload, offline),
    15000,
  );
  window.addEventListener(
    "pagehide",
    () => {
      window.clearInterval(timer);
      window.clearInterval(ages);
    },
    { once: true },
  );
}
const host = document.querySelector("[data-household-presence]");
if (host) mountPresence(host);
