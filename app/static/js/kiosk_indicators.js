const LABELS = {
  door: "Door or window opened",
  person: "Person detected outside",
  package: "Package detected",
  sms: "Text sent",
};

export function mountKioskIndicators(profile) {
  if (!["office", "living"].includes(profile)) return () => {};
  const css = document.createElement("link");
  css.rel = "stylesheet";
  css.href = "/static/css/kiosk_indicators.css?v=20260927-1";
  document.head.append(css);
  const node = document.createElement("aside");
  node.className = "kiosk-indicators";
  node.setAttribute("aria-label", "Home indicators");
  const notice = document.createElement("div");
  notice.className = "kiosk-indicator-notice";
  notice.setAttribute("role", "status");
  notice.hidden = true;
  const state = document.createElement("div");
  state.className = "kiosk-indicator-state";
  state.hidden = true;
  node.append(notice, state);
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
    notice.textContent =
      event.kind === "door" && event.label
        ? `${event.label} opened`
        : LABELS[event.kind];
    notice.hidden = false;
    expiry = setTimeout(
      () => {
        notice.hidden = true;
        showing = false;
        showNext();
      },
      Math.min(4500, event.until - Date.now()),
    );
  };
  const unavailable = () => {
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
            : "Privacy status unavailable";
        state.dataset.kind = data.privacy === "active" ? "privacy" : "unknown";
        state.hidden = false;
      } else state.hidden = true;
      for (const event of data.events || []) {
        if (!LABELS[event.kind] || !event.id || seen.has(event.id)) continue;
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
