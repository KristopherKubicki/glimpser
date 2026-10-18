function configuredSite(value) {
  return typeof value === "string" && value.trim() && value.length <= 240
    ? value.trim()
    : "";
}

const COVERAGE_REASONS = {
  read_failed: "hub read failed",
  stale_report: "sensor report is stale",
  missing_report: "no report time",
  clock_ahead: "sensor clock ahead",
  disabled: "sensor disabled",
  invalid_state: "contact state unavailable",
};

const LABELS = {
  door: "Door or window opened",
  person: "Person detected outside",
  package: "Package detected",
  sms: "Text sent",
};

const CUES = {
  main: "Main-floor movement",
  upstairs: "Upstairs movement",
  basement: "Basement movement",
  office: "Office movement",
  approach: "Movement toward the office",
  depart: "Movement away from the office",
  hour: "Top of the hour",
  mode: "House mode changed",
  settle: "House settling for the evening",
  "garage-open": "Garage left open",
  "garage-close": "Garage closed",
  "hal-yellow": "HAL warning",
  "hal-red": "HAL critical alert",
  "hal-clear": "HAL recovered",
  "hal-unknown": "HAL status unavailable",
};
const ageText = (seconds) =>
  seconds < 60 ? "just now" : `${Math.floor(seconds / 60)}m ago`;

const MOTION_ZONES = {
  main: ["main"],
  upstairs: ["upstairs"],
  basement: ["basement"],
  office: ["office"],
  approach: ["basement", "office"],
  depart: ["office", "basement"],
};

// Only a newly reported light cue produces a popup; heartbeat snapshots must
// never replay an old cue or imply that motion is still active.
export function onyxCueEvent(data) {
  const cue = data?.status?.cue;
  if (!data?.available || !cue || !Number.isFinite(cue.at)) return null;
  const label =
    CUES[cue.kind] ||
    (cue.kind?.startsWith("entry-")
      ? "Door-to-room movement"
      : cue.kind?.startsWith("open-")
        ? "Door left open reminder"
        : null);
  if (!label) return null;
  return {
    id: `onyx:${cue.kind}:${cue.at}`,
    kind: "onyx",
    at: cue.at,
    label,
    cueKind: cue.kind,
    zones: MOTION_ZONES[cue.kind] || [],
  };
}

function renderNotice(notice, event) {
  notice.replaceChildren();
  const title = document.createElement("strong");
  title.textContent =
    event.kind === "onyx"
      ? `Onyx · ${event.label}`
      : event.kind === "door" && event.label
        ? `${event.label} opened`
        : LABELS[event.kind];
  notice.append(title);
  if (event.kind !== "onyx") return;
  const detail = document.createElement("small");
  detail.className = "onyx-cue-detail";
  detail.textContent = event.zones.length
    ? "Motion reported just now"
    : "Light notification";
  notice.append(detail);
  if (!event.zones.length) return;
  const map = document.createElement("div");
  map.className = "onyx-house-map";
  map.setAttribute("aria-label", `House zones: ${event.label}`);
  for (const [zone, label] of [
    ["upstairs", "Upstairs"],
    ["main", "Main floor"],
    ["basement", "Basement"],
    ["office", "Office"],
  ]) {
    const room = document.createElement("div");
    room.className = "onyx-house-zone";
    room.dataset.zone = zone;
    room.dataset.active = String(event.zones.includes(zone));
    room.textContent = `${label}${event.zones.includes(zone) ? " · Motion" : ""}`;
    map.append(room);
  }
  notice.append(map);
}

export function officeRows(status, now) {
  if (!status) return [];
  const rows = [];
  const hal = status.hal || {};
  const stale =
    !Number.isFinite(hal.updated) ||
    now - hal.updated > 120 ||
    hal.updated > now + 5;
  const level =
    hal.level === "disabled" ? "disabled" : stale ? "unknown" : hal.level;
  const titles = {
    normal: "HAL healthy",
    yellow: "HAL needs attention",
    red: "HAL critical alert",
    unknown: "HAL status unavailable",
    starting: "Checking HAL",
  };
  if (titles[level]) {
    const metrics = hal.metrics || {};
    const readings = [];
    if (!stale && Number.isFinite(metrics.temperature))
      readings.push(`${Math.round(metrics.temperature)}°C`);
    if (!stale && Number.isFinite(metrics.cpu))
      readings.push(`CPU ${Math.round(metrics.cpu)}%`);
    const clearing = level === "yellow" || level === "red";
    const detail = stale
      ? "Waiting for fresh readings; no all-clear assumed"
      : [
          hal.reason,
          readings.join(" · "),
          clearing ? "Clears after confirmed recovery" : "",
        ]
          .filter(Boolean)
          .join(" · ");
    rows.push({ kind: level, title: titles[level], detail });
  }
  if (status.garage?.open === true) {
    const since = status.garage.since;
    const minutes =
      since > 0 && since <= now ? Math.floor((now - since) / 60) : null;
    rows.push({
      kind: "yellow",
      title: "Garage is open",
      detail: `${minutes === null ? "" : `Open ${minutes < 1 ? "under 1 minute" : `${minutes}m`} · `}Clears when the door closes`,
    });
  }
  const cue = status.cue || {};
  const label =
    CUES[cue.kind] ||
    (cue.kind?.startsWith("entry-")
      ? "Door-to-room movement"
      : cue.kind?.startsWith("open-")
        ? "Door left open reminder"
        : null);
  if (
    label &&
    Number.isFinite(cue.at) &&
    now - cue.at >= -5 &&
    now - cue.at < 90
  ) {
    const active = cue.until > now && cue.until <= now + 60;
    rows.push({
      kind: "cue",
      title: active ? `Onyx · ${label}` : `Last cue · ${label}`,
      detail: active
        ? `Returns to normal in ${Math.ceil(cue.until - now)}s`
        : ageText(now - cue.at),
    });
  }
  return rows;
}

export function perimeterRows(data, now) {
  if (
    !data ||
    !Number.isFinite(data.checked_at) ||
    now - data.checked_at > 30 ||
    data.checked_at > now + 5 ||
    !Array.isArray(data.sensors) ||
    !data.sensors.length
  )
    return [
      {
        kind: "unknown",
        title: "Door / safe coverage unavailable",
        detail: "Waiting for fresh sensor readings",
      },
    ];
  const open = data.sensors.filter((sensor) => sensor.state === "open");
  const unknown = data.sensors.filter((sensor) => sensor.state === "unknown");
  const battery = data.sensors.filter((sensor) => sensor.low_battery);
  const rows = [];
  if (open.length)
    rows.push({
      kind: "yellow",
      openContacts: true,
      title: `${open.length} open ${open.length === 1 ? "door / safe" : "doors / safes"}`,
      detail: open
        .map((sensor) => {
          const elapsed =
            Number.isFinite(sensor.changed_at) && sensor.changed_at <= now
              ? Math.floor((now - sensor.changed_at) / 60)
              : null;
          return `${sensor.label}${elapsed === null ? " · duration unknown" : ` · ${elapsed < 1 ? "under 1m" : `${elapsed}m`}`}`;
        })
        .join("; "),
    });
  if (unknown.length)
    rows.push({
      kind: "unknown",
      title: `${unknown.length} sensor coverage ${unknown.length === 1 ? "gap" : "gaps"}`,
      detail: unknown
        .map(
          (sensor) =>
            `${sensor.label}${sensor.last_known === "open" ? " (last known open)" : ""}${sensor.reason ? ` · ${COVERAGE_REASONS[sensor.reason] || "state unavailable"}` : ""}`,
        )
        .join("; "),
    });
  if (battery.length)
    rows.push({
      kind: "yellow",
      title: "Sensor batteries need attention",
      detail: battery.map((sensor) => sensor.label).join("; "),
    });
  if (!open.length)
    rows.unshift({
      kind: unknown.length ? "unknown" : "normal",
      title: "No open contacts reported",
      detail: unknown.length
        ? "Incomplete coverage — unverified sensors are listed below"
        : "Configured contacts report closed; lock states are not included",
    });
  const site = configuredSite(data.site) || "Site unverified";
  rows.forEach((row) => {
    row.title = `${site} · ${row.title}`;
  });
  return rows;
}

export function teslaRows(data, now) {
  const current =
    data &&
    Number.isFinite(data.checked_at) &&
    now - data.checked_at >= -5 &&
    now - data.checked_at <= 300 &&
    Array.isArray(data.feeds) &&
    data.feeds.length === 6;
  if (!current)
    return [
      {
        kind: "unknown",
        title: "Tesla camera health unavailable",
        detail: "Waiting for capture health; saved images may be old",
        link: "/group/tesla",
      },
    ];
  const exterior = data.feeds.filter((row) =>
    ["Tesla-Front", "Tesla-Left", "Tesla-Right", "Tesla-Rear"].includes(
      row.name,
    ),
  );
  const fresh = exterior.filter((row) => row.state === "fresh").length;
  const live = data.workers?.live || {};
  const schedule =
    live.schedule === "active"
      ? "scheduled"
      : live.schedule === "inactive"
        ? "paused"
        : "schedule unavailable";
  const names = {
    "Tesla-Front": "Front",
    "Tesla-Left": "Left",
    "Tesla-Right": "Right",
    "Tesla-Rear": "Rear",
    "Tesla-App": "App",
    "Tesla-Map": "Map",
  };
  const ages = data.feeds
    .filter((row) => names[row.name])
    .map((row) => {
      const age = row.age_seconds;
      const text = !Number.isFinite(age)
        ? "unknown age"
        : age < 60
          ? "under 1m"
          : age < 3600
            ? `${Math.floor(age / 60)}m`
            : `${Math.floor(age / 3600)}h`;
      return `${names[row.name]} ${text}${row.state === "fresh" ? "" : " (stale)"}`;
    })
    .join(" · ");
  return [
    {
      kind: data.state === "ok" ? "normal" : "unknown",
      title: `Tesla · ${fresh}/4 recent cameras · ${schedule}`,
      detail: `${ages}. Periodic vehicle snapshots; location and motion unverified.${live.state === "failed" ? " Last camera attempt failed." : ""}`,
      link: "/group/tesla",
    },
  ];
}

export function openDoorNote(data, now = Date.now() / 1000) {
  if (
    !Number.isFinite(data?.server_time) ||
    now - data.server_time < -5 ||
    now - data.server_time > 10
  )
    return "";
  const perimeter = data.perimeter;
  const site = configuredSite(perimeter?.site);
  const doors = [];
  if (
    site &&
    Number.isFinite(perimeter.checked_at) &&
    now - perimeter.checked_at >= -5 &&
    now - perimeter.checked_at <= 30 &&
    Array.isArray(perimeter.sensors)
  ) {
    for (const sensor of perimeter.sensors) {
      if (
        sensor.attribute !== "contact" ||
        sensor.state !== "open" ||
        !Number.isFinite(sensor.changed_at) ||
        sensor.changed_at <= 0 ||
        now - sensor.changed_at < 120 ||
        typeof sensor.label !== "string"
      )
        continue;
      doors.push(
        `${sensor.label.slice(0, 60)} · open ${Math.floor((now - sensor.changed_at) / 60)}m`,
      );
    }
  }
  // The authenticated indicator producer also supplies an explicit garage
  // state. Do not use it to contradict a mapped contact or infer closed/locked.
  const garage = data.available === true ? data.status?.garage : null;
  const mappedGarage = perimeter?.sensors?.some?.(
    (s) => s.id === "401" && ["open", "closed"].includes(s.state),
  );
  if (
    !mappedGarage &&
    garage?.open === true &&
    Number.isFinite(garage.since) &&
    garage.since > 0 &&
    now - garage.since >= 120
  )
    doors.push(`Garage · open ${Math.floor((now - garage.since) / 60)}m`);
  if (!doors.length) return "";
  return `${site || "Site unverified"} · ${doors.slice(0, 2).join("; ")}${doors.length > 2 ? `; +${doors.length - 2} more — see Status` : ""}`;
}

export function mountKioskIndicators(profile) {
  if (!["office", "living"].includes(profile)) return () => {};
  const css = document.createElement("link");
  css.rel = "stylesheet";
  css.href = "/static/css/kiosk_indicators.css?v=20261005-onyx-map";
  document.head.append(css);
  const node = document.createElement("aside");
  node.className = "kiosk-indicators";
  node.setAttribute("aria-label", "Home indicators");
  const notice = document.createElement("div");
  notice.className = "kiosk-indicator-notice";
  notice.setAttribute("role", "status");
  notice.hidden = true;
  const doorNote = document.createElement("div");
  doorNote.className = "kiosk-indicator-notice";
  doorNote.dataset.kind = "open-contact";
  doorNote.setAttribute("role", "status");
  doorNote.hidden = true;
  let doorNoteExpiry;
  const renderDoorNote = (data) => {
    clearTimeout(doorNoteExpiry);
    const text = profile === "office" ? openDoorNote(data) : "";
    if (doorNote.textContent !== text) doorNote.textContent = text;
    doorNote.hidden = !text;
    if (text)
      doorNoteExpiry = setTimeout(
        () => {
          doorNote.hidden = true;
        },
        Math.max(0, Math.min(10, 10 - (Date.now() / 1000 - data.server_time))) *
          1000,
      );
  };
  const state = document.createElement("div");
  state.className = "kiosk-indicator-state";
  state.hidden = true;
  const office = document.createElement("section");
  office.className = "kiosk-office-status";
  office.setAttribute("aria-label", "Office and Onyx status");
  office.hidden = true;
  const perimeter = document.createElement("details");
  perimeter.className = "kiosk-perimeter-status";
  perimeter.setAttribute(
    "aria-label",
    "Doors, sensitive areas, and Tesla camera coverage",
  );
  // Rotating screens stay quiet at every size. Details open only on request.
  const summary = document.createElement("summary");
  const content = document.createElement("div");
  perimeter.append(summary, content, office);
  let perimeterSignature = "";
  const renderPerimeter = (data) => {
    const rows = perimeterRows(
      data?.perimeter,
      data?.server_time || Date.now() / 1000,
    );
    rows.push(
      ...teslaRows(data?.tesla, data?.server_time || Date.now() / 1000),
    );
    const signature = JSON.stringify([rows, data?.status, data?.available]);
    if (signature === perimeterSignature) return;
    content.replaceChildren();
    const opening = rows.find((row) => row.openContacts === true);
    const officeAlerts = data?.available
      ? officeRows(data.status, data.server_time).filter((row) =>
          ["yellow", "red"].includes(row.kind),
        )
      : [];
    const urgent = officeAlerts.find((row) => row.kind === "red");
    const attention = rows.some((row) =>
      ["unknown", "yellow"].includes(row.kind),
    );
    summary.textContent = opening
      ? `${opening.title} · Status`
      : urgent
        ? "HAL alert · Status"
        : officeAlerts.length
          ? `${officeAlerts[0].title} · Status`
          : attention
            ? "Status · needs attention"
            : "Status";
    summary.dataset.kind =
      opening || urgent || officeAlerts.length ? "alert" : "quiet";
    for (const row of rows) {
      const card = document.createElement("div");
      card.className = "kiosk-office-card";
      card.dataset.kind = row.kind;
      const title = document.createElement("strong");
      title.textContent = row.title;
      const detail = document.createElement("span");
      detail.textContent = row.detail;
      card.append(title, detail);
      if (row.link) {
        const link = document.createElement("a");
        link.href = row.link;
        link.textContent = "View Tesla cameras and saved clips";
        card.append(link);
      }
      content.append(card);
    }
    perimeterSignature = signature;
  };
  node.append(notice, doorNote, state, perimeter);
  let officeSignature = "";
  const renderOffice = (data) => {
    if (profile !== "office" || !data.available || !data.status) {
      office.hidden = true;
      officeSignature = "";
      return;
    }
    const rows = officeRows(data.status, data.server_time);
    const phase =
      { day: "Daytime", evening: "Warm evening", night: "Dim nighttime" }[
        data.status.phase
      ] || "";
    const footer = [
      phase,
      data.status.quiet ? "Light cues paused" : "Onyx indicators",
    ]
      .filter(Boolean)
      .join(" · ");
    const signature = JSON.stringify([rows, footer]);
    if (signature !== officeSignature) {
      office.replaceChildren();
      for (const row of rows) {
        const card = document.createElement("div");
        card.className = "kiosk-office-card";
        card.dataset.kind = row.kind;
        const title = document.createElement("strong");
        title.textContent = row.title;
        const detail = document.createElement("span");
        detail.textContent = row.detail;
        card.append(title, detail);
        office.append(card);
      }
      const phaseLabel = document.createElement("small");
      phaseLabel.textContent = footer;
      office.append(phaseLabel);
      officeSignature = signature;
    }
    office.hidden = false;
  };
  document.body.append(node);
  const key = `glimpser.indicators.seen.${profile}`;
  let seen;
  try {
    seen = new Set(JSON.parse(localStorage.getItem(key) || "[]"));
  } catch {
    seen = new Set();
  }
  let disposed = false,
    pending = false,
    timer,
    expiry,
    controller;
  let queue = [];
  let showing = false;
  const remember = (id) => {
    seen.add(id);
    seen = new Set([...seen].slice(-64));
    try {
      localStorage.setItem(key, JSON.stringify([...seen]));
    } catch {
      /* private browser */
    }
  };
  const showNext = () => {
    if (disposed || showing) return;
    queue = queue.filter((e) => e.until > Date.now());
    const event = queue.shift();
    if (!event) return;
    showing = true;
    notice.dataset.kind = event.kind;
    renderNotice(notice, event);
    notice.hidden = false;
    expiry = setTimeout(
      () => {
        notice.hidden = true;
        showing = false;
        showNext();
      },
      Math.min(event.kind === "onyx" ? 6000 : 4500, event.until - Date.now()),
    );
  };
  const unavailable = () => {
    renderDoorNote(null);
    renderPerimeter(null);
    office.hidden = true;
    officeSignature = "";
    state.textContent = "Indicator connection unavailable";
    state.dataset.kind = "unknown";
    state.hidden = false;
  };
  const poll = async () => {
    if (disposed || pending || document.hidden) return;
    pending = true;
    controller =
      typeof AbortController === "function" ? new AbortController() : null;
    const timeout = setTimeout(() => controller?.abort(), 3000);
    try {
      const response = await fetch(`/kiosk_indicators?profile=${profile}`, {
        cache: "no-store",
        signal: controller?.signal,
      });
      if (!response.ok) throw new Error("unavailable");
      const data = await response.json();
      if (disposed) return;
      if (!data.available) unavailable();
      else if (profile === "office" && data.privacy !== "inactive") {
        state.textContent =
          data.privacy === "active"
            ? "Privacy mode on"
            : "Browser privacy not reporting";
        state.dataset.kind = data.privacy === "active" ? "privacy" : "unknown";
        state.hidden = false;
      } else state.hidden = true;
      renderOffice(data);
      renderPerimeter(data);
      renderDoorNote(data);
      const events = [...(data.events || [])];
      const cue = profile === "office" ? onyxCueEvent(data) : null;
      if (cue) events.push(cue);
      for (const event of events) {
        if (
          (!LABELS[event.kind] && event !== cue) ||
          !event.id ||
          seen.has(event.id)
        )
          continue;
        remember(event.id);
        const age = data.server_time - event.at;
        if (!Number.isFinite(age) || age < -5 || age > 10) continue;
        queue.push({
          ...event,
          until: Date.now() + Math.min(6000, (10 - age) * 1000),
        });
      }
      queue = queue.slice(-8);
      showNext();
    } catch {
      if (!disposed) unavailable();
    } finally {
      clearTimeout(timeout);
      pending = false;
    }
  };
  const dispose = () => {
    disposed = true;
    controller?.abort();
    clearTimeout(expiry);
    clearTimeout(doorNoteExpiry);
    clearInterval(timer);
    document.removeEventListener("visibilitychange", visible);
    node.remove();
    css.remove();
  };
  const visible = () => {
    if (!document.hidden) void poll();
  };
  document.addEventListener("visibilitychange", visible);
  window.addEventListener("pagehide", dispose, { once: true });
  timer = setInterval(poll, 1000);
  void poll();
  return dispose;
}
